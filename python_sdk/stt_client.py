"""STT (Speech-to-Text) client for real-time speech recognition."""

import asyncio
import json
import ssl
import uuid
import gzip
import struct
import time
from typing import Optional, Callable, Dict, Any, List, Tuple, AsyncGenerator
from enum import Enum
from dataclasses import dataclass
from collections import deque
import websockets
from loguru import logger

# Protocol constants
PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

# Message Type
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_ERROR_RESPONSE = 0b1111

# Message Type Specific Flags
NO_SEQUENCE = 0b0000
POS_SEQUENCE = 0b0001
NEG_SEQUENCE = 0b0010
NEG_WITH_SEQUENCE = 0b0011

# Serialization Type
NO_SERIALIZATION = 0b0000
JSON = 0b0001

# Compression Type
COMPRESSION_NO = 0b0000
COMPRESSION_GZIP = 0b0001

# Default settings
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SEGMENT_DURATION = 200  # ms


class STTStatus(Enum):
    """STT状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECOGNIZING = "recognizing"
    ERROR = "error"


@dataclass
class STTConfig:
    """STT配置类"""
    audio_format: str = "wav"
    sample_rate: int = 16000
    channels: int = 1
    bits: int = 16
    language: str = "zh-CN"
    enable_punctuation: bool = True
    enable_itn: bool = True
    enable_ddc: bool = True
    show_utterances: bool = True
    enable_nonstream: bool = False
    segment_duration: int = 200


@dataclass
class STTSession:
    """STT会话信息"""
    session_id: str
    start_time: float
    config: STTConfig
    status: STTStatus
    total_audio_bytes: int = 0
    total_results: int = 0
    final_results: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class Header:
    def __init__(
        self,
        protocol_version=PROTOCOL_VERSION,
        header_size=DEFAULT_HEADER_SIZE,
        message_type: int = 0,
        message_type_specific_flags: int = 0,
        serial_method: int = NO_SERIALIZATION,
        compression_type: int = COMPRESSION_NO,
        reserved_data=0,
    ):
        self.header_size = header_size
        self.protocol_version = protocol_version
        self.message_type = message_type
        self.message_type_specific_flags = message_type_specific_flags
        self.serial_method = serial_method
        self.compression_type = compression_type
        self.reserved_data = reserved_data

    def as_bytes(self) -> bytes:
        return bytes(
            [
                (self.protocol_version << 4) | self.header_size,
                (self.message_type << 4) | self.message_type_specific_flags,
                (self.serial_method << 4) | self.compression_type,
                self.reserved_data,
            ]
        )


class CommonUtils:
    @staticmethod
    def gzip_compress(data: bytes) -> bytes:
        return gzip.compress(data)

    @staticmethod
    def gzip_decompress(data: bytes) -> bytes:
        return gzip.decompress(data)

    @staticmethod
    def validate_pcm_audio(audio_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bool:
        """验证PCM音频数据格式"""
        try:
            if len(audio_data) % 2 != 0:
                return False
            
            expected_bytes_per_second = sample_rate * channels * 2
            max_expected_length = expected_bytes_per_second * 10
            
            if len(audio_data) > max_expected_length:
                logger.warning(f"Audio data too large: {len(audio_data)} bytes")
                return False
            
            return True
        except Exception as e:
            logger.error(f"PCM validation failed: {e}")
            return False
    
    @staticmethod
    def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
        """将PCM数据转换为WAV格式"""
        import struct
        
        # WAV文件头
        wav_header = bytearray()
        
        # RIFF头
        wav_header.extend(b'RIFF')
        wav_header.extend(struct.pack('<I', 36 + len(pcm_data)))  # 文件大小
        wav_header.extend(b'WAVE')
        
        # fmt子块
        wav_header.extend(b'fmt ')
        wav_header.extend(struct.pack('<I', 16))  # fmt子块大小
        wav_header.extend(struct.pack('<H', 1))   # 音频格式 (PCM)
        wav_header.extend(struct.pack('<H', channels))  # 声道数
        wav_header.extend(struct.pack('<I', sample_rate))  # 采样率
        wav_header.extend(struct.pack('<I', sample_rate * channels * bits // 8))  # 字节率
        wav_header.extend(struct.pack('<H', channels * bits // 8))  # 块对齐
        wav_header.extend(struct.pack('<H', bits))  # 位深度
        
        # data子块
        wav_header.extend(b'data')
        wav_header.extend(struct.pack('<I', len(pcm_data)))  # 数据大小
        
        # 组合WAV文件
        wav_data = bytes(wav_header) + pcm_data
        return wav_data


class STTResponse:
    def __init__(self):
        self.code = 0
        self.event = 0
        self.is_last_package = False
        self.payload_sequence = 0
        self.payload_size = 0
        self.payload_msg = None
        self.text = ""
        self.final = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "event": self.event,
            "is_last_package": self.is_last_package,
            "payload_sequence": self.payload_sequence,
            "payload_size": self.payload_size,
            "payload_msg": self.payload_msg,
            "text": self.text,
            "final": self.final
        }


class ResponseParser:
    @staticmethod
    def parse_response(msg: bytes) -> STTResponse:
        response = STTResponse()

        header_size = msg[0] & 0x0f
        message_type = msg[1] >> 4
        message_type_specific_flags = msg[1] & 0x0f
        serialization_method = msg[2] >> 4
        message_compression = msg[2] & 0x0f

        payload = msg[header_size*4:]

        # Parse message_type_specific_flags
        if message_type_specific_flags & 0x01:
            response.payload_sequence = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]
        if message_type_specific_flags & 0x02:
            response.is_last_package = True
        if message_type_specific_flags & 0x04:
            response.event = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]

        # Parse message_type
        if message_type == SERVER_FULL_RESPONSE:
            response.payload_size = struct.unpack('>I', payload[:4])[0]
            payload = payload[4:]
        elif message_type == SERVER_ERROR_RESPONSE:
            response.code = struct.unpack('>i', payload[:4])[0]
            response.payload_size = struct.unpack('>I', payload[4:8])[0]
            payload = payload[8:]

        if not payload:
            return response

        # Decompress payload
        if message_compression == COMPRESSION_GZIP:
            try:
                payload = CommonUtils.gzip_decompress(payload)
            except Exception as e:
                logger.error(f"Failed to decompress payload: {e}")
                return response

        # Parsing the Payload
        try:
            if serialization_method == JSON:
                response.payload_msg = json.loads(payload.decode('utf-8'))
                # Extract text from payload
                if response.payload_msg and isinstance(response.payload_msg, dict):
                    if 'result' in response.payload_msg:
                        result = response.payload_msg['result']
                        if isinstance(result, dict) and 'text' in result:
                            response.text = result['text']
                            response.final = result.get('final', False)
        except Exception as e:
            logger.error(f"Failed to parse payload: {e}")

        return response


class RequestBuilder:
    @staticmethod
    def new_auth_headers(app_key: str, access_key: str) -> Dict[str, str]:
        reqid = str(uuid.uuid4())
        return {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": reqid,
            "X-Api-Access-Key": access_key,
            "X-Api-App-Key": app_key
        }

    @staticmethod
    def new_full_client_request(seq: int, config: STTConfig) -> bytes:
        header = Header(
            message_type=CLIENT_FULL_REQUEST,
            message_type_specific_flags=POS_SEQUENCE,
            serial_method=JSON,
            compression_type=COMPRESSION_GZIP
        )

        payload = {
            "user": {
                "uid": "demo_uid"
            },
            "audio": {
                "format": config.audio_format,
                "codec": "raw",
                "rate": config.sample_rate,
                "bits": config.bits,
                "channel": config.channels
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": config.enable_itn,
                "enable_punc": config.enable_punctuation,
                "enable_ddc": config.enable_ddc,
                "show_utterances": config.show_utterances,
                "enable_nonstream": config.enable_nonstream
            }
        }

        payload_bytes = json.dumps(payload).encode('utf-8')
        compressed_payload = CommonUtils.gzip_compress(payload_bytes)
        payload_size = len(compressed_payload)

        request = bytearray()
        request.extend(header.as_bytes())
        request.extend(struct.pack('>i', seq))
        request.extend(struct.pack('>I', payload_size))
        request.extend(compressed_payload)

        return bytes(request)

    @staticmethod
    def new_audio_only_request(seq: int, segment: bytes, is_last: bool = False) -> bytes:
        header = Header(
            message_type=CLIENT_AUDIO_ONLY_REQUEST,
            message_type_specific_flags=NEG_WITH_SEQUENCE if is_last else POS_SEQUENCE,
            compression_type=COMPRESSION_GZIP
        )

        request = bytearray()
        request.extend(header.as_bytes())
        request.extend(struct.pack('>i', -seq if is_last else seq))  # 最后一条消息使用负序列号

        compressed_segment = CommonUtils.gzip_compress(segment)
        request.extend(struct.pack('>I', len(compressed_segment)))
        request.extend(compressed_segment)

        return bytes(request)

        return bytes(request)


class STTClient:
    """增强的STT客户端"""
    
    def __init__(self, app_key: str, access_key: str, resource_id: str = "volc.bigasr.sauc.duration",
                 verify_ssl: bool = True, config: Optional[STTConfig] = None):
        """初始化STT客户端"""
        self.app_key = app_key
        self.access_key = access_key
        self.resource_id = resource_id
        self.verify_ssl = verify_ssl
        self.config = config or STTConfig()
        
        # 连接状态
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.status = STTStatus.DISCONNECTED
        self.is_connected = False
        
        # 会话管理
        self.current_session: Optional[STTSession] = None
        self.session_history: List[STTSession] = []
        
        # 任务管理
        self.recognition_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None
        
        # 音频缓冲
        self.audio_buffer = deque(maxlen=1000)
        self.buffer_size = 0
        
        # 序列号管理 - 确保从1开始
        self.seq = 1
        self._seq_lock = asyncio.Lock()  # 添加序列号锁
        
        # 重连配置
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1.0
        self.current_reconnect_attempts = 0
        
        # 统计信息
        self.stats = {
            "total_sessions": 0,
            "total_audio_bytes": 0,
            "total_results": 0,
            "total_errors": 0,
            "connection_time": 0,
            "last_activity": 0
        }
        
        # 回调函数
        self.on_result: Optional[Callable[[str, bool], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_status_change: Optional[Callable[[STTStatus], None]] = None
        
        # 锁机制
        self._lock = asyncio.Lock()
        
    async def connect(self, url: str = "wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel_nostream") -> bool:
        """连接到STT服务"""
        async with self._lock:
            if self.status == STTStatus.CONNECTING:
                return False
            
            self.status = STTStatus.CONNECTING
            self._notify_status_change()
            
            try:
                # 构建认证头
                headers = RequestBuilder.new_auth_headers(self.app_key, self.access_key)
                headers["X-Api-Resource-Id"] = self.resource_id
                
                logger.info(f"尝试连接STT服务: {url}")
                
                # SSL配置
                if self.verify_ssl:
                    ssl_context = ssl.create_default_context()
                else:
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                
                # 尝试连接
                self.websocket = await websockets.connect(
                    url,
                    additional_headers=headers,
                    ssl=ssl_context,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=10
                )
                
                # 验证连接状态
                if self.websocket and self.websocket.state == websockets.protocol.State.OPEN:
                    self.status = STTStatus.CONNECTED
                    self.is_connected = True
                    self.current_reconnect_attempts = 0
                    self.stats["connection_time"] = time.time()
                    self.stats["last_activity"] = time.time()
                    
                    # 发送初始请求
                    await self._send_full_client_request()
                    
                    # 启动心跳任务
                    self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    
                    logger.info("STT client connected successfully")
                    self._notify_status_change()
                    return True
                else:
                    raise Exception("WebSocket connection not in OPEN state")
                    
            except Exception as e:
                logger.error(f"STT连接失败: {e}")
                self.status = STTStatus.ERROR
                self.is_connected = False
                self._notify_status_change()
                return False
    
    async def disconnect(self) -> None:
        """断开STT连接"""
        async with self._lock:
            try:
                if self.recognition_task:
                    self.recognition_task.cancel()
                    self.recognition_task = None
                
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                    self.heartbeat_task = None
                
                if self.reconnect_task:
                    self.reconnect_task.cancel()
                    self.reconnect_task = None
                
                if self.websocket:
                    await self.websocket.close()
                    self.websocket = None
                
                self.status = STTStatus.DISCONNECTED
                self.is_connected = False
                self.current_session = None
                self.audio_buffer.clear()
                self.buffer_size = 0
                
                logger.info("STT client disconnected")
                self._notify_status_change()
                
            except Exception as e:
                logger.error(f"Error disconnecting STT client: {e}")
    
    async def start_recognition(self, 
                               on_result: Optional[Callable[[str, bool], None]] = None,
                               on_error: Optional[Callable[[str], None]] = None,
                               session_config: Optional[STTConfig] = None) -> bool:
        """开始语音识别"""
        if not self.is_connected:
            logger.error("STT client not connected")
            return False
        
        try:
            self.on_result = on_result
            self.on_error = on_error
            
            config = session_config or self.config
            
            session_id = f"stt_session_{int(time.time() * 1000)}"
            self.current_session = STTSession(
                session_id=session_id,
                start_time=time.time(),
                config=config,
                status=STTStatus.RECOGNIZING
            )
            
            # 保持序列号连续性，不重置序列号
            # self.seq = 2  # 注释掉这行，保持序列号连续性
            
            logger.info(f"STT recognition started for session: {session_id} with seq: {self.seq}")
            
            # 只有在没有运行中的识别任务时才创建新任务
            if not self.recognition_task or self.recognition_task.done():
                self.recognition_task = asyncio.create_task(
                    self._listen_recognition_results()
                )
                logger.debug("已启动识别任务")
            else:
                logger.debug("识别任务已在运行，无需重新启动")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start STT recognition: {e}")
            if self.on_error:
                self.on_error(str(e))
            return False
    
    async def stop_recognition(self) -> bool:
        """停止语音识别"""
        try:
            if self.recognition_task:
                self.recognition_task.cancel()
                self.recognition_task = None
            
            if self.current_session:
                self.current_session.status = STTStatus.CONNECTED
                self.session_history.append(self.current_session)
                self.stats["total_sessions"] += 1
                
                self.current_session = None
                logger.info("STT recognition stopped")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop STT recognition: {e}")
            return False

    async def reset_session(self) -> bool:
        """重置会话状态，保持连接"""
        try:
            logger.info("开始重置STT会话状态")
            
            # 保存当前会话到历史
            if self.current_session:
                self.current_session.status = STTStatus.CONNECTED
                self.session_history.append(self.current_session)
                logger.debug(f"已保存会话到历史: {self.current_session.session_id}")
            
            # 重置关键状态 - 保持序列号连续性，不从1开始重置
            # self.seq = 1  # 注释掉这行，保持序列号连续性
            self.audio_buffer.clear()  # 清空音频缓冲区
            self.buffer_size = 0
            logger.debug("已清空音频缓冲区，保持序列号连续性")
            
            # 创建新会话
            session_id = f"stt_session_{int(time.time() * 1000)}"
            self.current_session = STTSession(
                session_id=session_id,
                start_time=time.time(),
                config=self.config,
                status=STTStatus.RECOGNIZING
            )
            logger.debug(f"已创建新会话: {session_id}")
            
            # 不再重新启动识别任务，因为监听循环会持续运行
            # 只有在第一次启动时才创建识别任务
            if not self.recognition_task or self.recognition_task.done():
                self.recognition_task = asyncio.create_task(
                    self._listen_recognition_results()
                )
                logger.debug("已启动识别任务")
            else:
                logger.debug("识别任务已在运行，无需重新启动")
            
            logger.info(f"STT会话重置成功: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"重置STT会话失败: {e}")
            if self.on_error:
                self.on_error(f"Session reset failed: {str(e)}")
            return False
    
    async def send_audio(self, audio_data: bytes, is_last: bool = False) -> bool:
        """发送音频数据进行识别"""
        if not self.is_connected:
            logger.error(f"🔍 STT客户端未连接: connected={self.is_connected}")
            return False
            
        if not self.current_session:
            logger.error(f"🔍 STT会话不存在: session={self.current_session is not None}")
            return False
            
        if not self.websocket or self.websocket.state != websockets.protocol.State.OPEN:
            logger.error(f"🔍 WebSocket连接状态异常: websocket={self.websocket is not None}, state={self.websocket.state if self.websocket else 'None'}")
            return False
        
        async with self._seq_lock:  # 使用序列号锁确保线程安全
            try:
                # 将PCM数据转换为WAV格式
                wav_audio_data = CommonUtils.pcm_to_wav(
                    audio_data, 
                    self.current_session.config.sample_rate,
                    self.current_session.config.channels,
                    self.current_session.config.bits
                )
                
                if not CommonUtils.validate_pcm_audio(audio_data, 
                                                     self.current_session.config.sample_rate,
                                                     self.current_session.config.channels):
                    logger.warning("Invalid PCM audio data")
                    return False
                
                self.audio_buffer.append(audio_data)
                self.buffer_size += len(audio_data)
                self.current_session.total_audio_bytes += len(audio_data)
                self.stats["total_audio_bytes"] += len(audio_data)
                
                # 构建音频请求 - 使用当前序列号，发送WAV格式数据
                current_seq = self.seq
                logger.debug(f"🔍 发送音频数据 - 序列号: {current_seq}, 会话: {self.current_session.session_id}, 数据长度: {len(wav_audio_data)}")
                request = RequestBuilder.new_audio_only_request(current_seq, wav_audio_data, is_last)
                await self.websocket.send(request)
                
                # 只有在成功发送后才增加序列号
                self.seq += 1
                self.stats["last_activity"] = time.time()
                logger.debug(f"🔍 音频数据发送成功 - 新序列号: {self.seq}")
                
                return True
                
            except Exception as e:
                logger.error(f"🔍 STT音频发送失败: {e}")
                if self.on_error:
                    self.on_error(f"Audio send failed: {str(e)}")
                return False
    
    async def _send_full_client_request(self):
        """发送完整的客户端请求"""
        async with self._seq_lock:  # 使用序列号锁确保线程安全
            current_seq = self.seq
            request = RequestBuilder.new_full_client_request(current_seq, self.config)
            await self.websocket.send(request)
            self.seq += 1  # 在发送后增加序列号
            logger.info(f"Sent full client request with seq: {current_seq}")
    
    async def _listen_recognition_results(self) -> None:
        """监听识别结果"""
        try:
            while self.is_connected and self.websocket and self.current_session:
                try:
                    message = await self.websocket.recv()
                    
                    if isinstance(message, bytes):
                        response = ResponseParser.parse_response(message)
                        
                        self.stats["last_activity"] = time.time()
                        
                        if response.text:
                            self.current_session.total_results += 1
                            if response.final:
                                self.current_session.final_results += 1
                            self.stats["total_results"] += 1
                            
                            logger.debug(f"STTClient: Calling on_result callback. Is it None? {self.on_result is None}")
                            if self.on_result:
                                self.on_result(response.text, response.final)
                            
                            logger.debug(f"STT result: {response.text} (final: {response.final})")
                        
                        if response.code != 0:
                            error_msg = f"STT Error {response.code}: {response.payload_msg}"
                            self.current_session.errors.append(error_msg)
                            self.stats["total_errors"] += 1
                            
                            if self.on_error:
                                self.on_error(error_msg)
                            
                            logger.error(f"STT error: {error_msg}")
                        
                        if response.is_last_package:
                            logger.info(f"STT session ended: {self.current_session.session_id}")
                            # 不要break退出循环，继续监听新的会话
                            # break
                        
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("STT connection closed during recognition")
                    break
                except Exception as e:
                    logger.error(f"Error processing STT message: {e}")
                    if self.on_error:
                        self.on_error(f"Message processing error: {str(e)}")
                    
        except Exception as e:
            logger.error(f"STT recognition listening error: {e}")
            if self.on_error:
                self.on_error(str(e))
    
    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        try:
            while self.is_connected and self.websocket:
                try:
                    await asyncio.sleep(30)
                    if self.websocket and self.websocket.state == websockets.protocol.State.OPEN:
                        await self.websocket.ping()
                except Exception as e:
                    logger.warning(f"Heartbeat failed: {e}")
                    break
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")
    
    def is_healthy(self) -> bool:
        """检查STT客户端健康状态"""
        return (self.is_connected and 
                self.websocket is not None and 
                self.websocket.state == websockets.protocol.State.OPEN and
                self.current_session is not None)
    
    async def _reconnect_loop(self) -> None:
        """重连循环"""
        try:
            while self.current_reconnect_attempts < self.max_reconnect_attempts:
                self.current_reconnect_attempts += 1
                delay = self.reconnect_delay * (2 ** (self.current_reconnect_attempts - 1))
                
                logger.info(f"Attempting to reconnect (attempt {self.current_reconnect_attempts}/{self.max_reconnect_attempts}) in {delay}s")
                await asyncio.sleep(delay)
                
                if await self.connect():
                    logger.info("Reconnection successful")
                    return
                else:
                    logger.warning(f"Reconnection attempt {self.current_reconnect_attempts} failed")
            
            logger.error("Max reconnection attempts reached")
            self.status = STTStatus.ERROR
            self._notify_status_change()
            
        except asyncio.CancelledError:
            logger.debug("Reconnect loop cancelled")
        except Exception as e:
            logger.error(f"Reconnect loop error: {e}")
    
    async def reconnect(self) -> bool:
        """手动重连"""
        if self.reconnect_task and not self.reconnect_task.done():
            logger.warning("Reconnection already in progress")
            return False
        
        self.reconnect_task = asyncio.create_task(self._reconnect_loop())
        return True
    
    async def health_check(self) -> bool:
        """执行健康检查"""
        try:
            if not self.is_connected or not self.websocket:
                return False
            
            if self.websocket.state != websockets.protocol.State.OPEN:
                return False
            
            if time.time() - self.stats["last_activity"] > 60:
                logger.warning("STT connection inactive for too long")
                return False
            
            pong_waiter = await self.websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=5.0)
            
            return True
            
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        current_session_stats = {}
        if self.current_session:
            current_session_stats = {
                "session_id": self.current_session.session_id,
                "duration": time.time() - self.current_session.start_time,
                "total_audio_bytes": self.current_session.total_audio_bytes,
                "total_results": self.current_session.total_results,
                "final_results": self.current_session.final_results,
                "errors": len(self.current_session.errors)
            }
        
        return {
            "status": self.status.value,
            "is_connected": self.is_connected,
            "current_session": current_session_stats,
            "session_history": len(self.session_history),
            "audio_buffer_size": self.buffer_size,
            "audio_buffer_count": len(self.audio_buffer),
            "reconnect_attempts": self.current_reconnect_attempts,
            "stats": self.stats.copy()
        }
    
    def _notify_status_change(self) -> None:
        """通知状态变化"""
        if self.on_status_change:
            self.on_status_change(self.status)
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.is_connected and self.websocket is not None and self.websocket.state == websockets.protocol.State.OPEN
    
    def get_current_session(self) -> Optional[STTSession]:
        """获取当前会话"""
        return self.current_session
    
    def get_session_history(self) -> List[STTSession]:
        """获取会话历史"""
        return self.session_history.copy()
    
    def clear_audio_buffer(self) -> None:
        """清空音频缓冲"""
        self.audio_buffer.clear()
        self.buffer_size = 0
        logger.info("Audio buffer cleared")
    
    def set_callbacks(self, 
                     on_result: Optional[Callable[[str, bool], None]] = None,
                     on_error: Optional[Callable[[str], None]] = None,
                     on_status_change: Optional[Callable[[STTStatus], None]] = None) -> None:
        """设置回调函数"""
        self.on_result = on_result
        self.on_error = on_error
        self.on_status_change = on_status_change


# 添加音频处理工具类
class AudioProcessor:
    """音频处理器"""
    
    @staticmethod
    def judge_wav(data: bytes) -> bool:
        """判断是否为WAV格式"""
        if len(data) < 44:
            return False
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    
    @staticmethod
    def read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
        """读取WAV文件信息"""
        if len(data) < 44:
            raise ValueError("Invalid WAV file: too short")
            
        # Parsing WAV header
        chunk_id = data[:4]
        if chunk_id != b'RIFF':
            raise ValueError("Invalid WAV file: not RIFF format")
            
        format_ = data[8:12]
        if format_ != b'WAVE':
            raise ValueError("Invalid WAV file: not WAVE format")
            
        # Parse fmt subchunk
        audio_format = struct.unpack('<H', data[20:22])[0]
        num_channels = struct.unpack('<H', data[22:24])[0]
        sample_rate = struct.unpack('<I', data[24:28])[0]
        bits_per_sample = struct.unpack('<H', data[34:36])[0]
        
        # Find the data sub-block
        pos = 36
        while pos < len(data) - 8:
            subchunk_id = data[pos:pos+4]
            subchunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
            if subchunk_id == b'data':
                wave_data = data[pos+8:pos+8+subchunk_size]
                return (
                    num_channels,
                    bits_per_sample // 8,
                    sample_rate,
                    subchunk_size // (num_channels * (bits_per_sample // 8)),
                    wave_data
                )
            pos += 8 + subchunk_size
            
        raise ValueError("Invalid WAV file: no data subchunk found")
    
    @staticmethod
    def get_segment_size(content: bytes, segment_duration: int = 200) -> int:
        """计算音频分段大小"""
        try:
            channel_num, samp_width, frame_rate, _, _ = AudioProcessor.read_wav_info(content)[:5]
            size_per_sec = channel_num * samp_width * frame_rate
            segment_size = size_per_sec * segment_duration // 1000
            return segment_size
        except Exception as e:
            logger.error(f"Failed to calculate segment size: {e}")
            raise
    
    @staticmethod
    def split_audio(data: bytes, segment_size: int) -> List[bytes]:
        """分割音频数据"""
        if segment_size <= 0:
            return []
            
        segments = []
        for i in range(0, len(data), segment_size):
            end = i + segment_size
            if end > len(data):
                end = len(data)
            segments.append(data[i:end])
        return segments


class SpeechToTextProcessor:
    """语音转文字处理器"""
    
    def __init__(self):
        self.current_text = ""
        self.final_text = ""
        self.is_processing = False
        
    def process_response(self, response: STTResponse) -> str:
        """处理ASR响应，返回识别的文字"""
        if response.code != 0:
            logger.error(f"ASR错误: {response.payload_msg}")
            return ""
            
        text = self._extract_text(response)
        if not text:
            return ""
            
        # 判断是否为最终结果
        if self._is_final_result(response):
            self.final_text = text
            self.is_processing = False
            return f"最终结果: {text}"
        else:
            # 中间结果
            self.current_text = text
            self.is_processing = True
            return f"识别中: {text}"
    
    def _extract_text(self, response: STTResponse) -> str:
        """提取识别出的文字"""
        if not response.payload_msg:
            return ""
        
        try:
            # 根据不同的响应格式提取文字
            if isinstance(response.payload_msg, dict):
                # 检查是否有result字段
                if 'result' in response.payload_msg:
                    result = response.payload_msg['result']
                    if isinstance(result, dict) and 'text' in result:
                        return result['text']
                    elif isinstance(result, str):
                        return result
                
                # 检查是否有text字段
                if 'text' in response.payload_msg:
                    return response.payload_msg['text']
                
                # 检查是否有sentence字段
                if 'sentence' in response.payload_msg:
                    sentence = response.payload_msg['sentence']
                    if isinstance(sentence, list) and len(sentence) > 0:
                        return sentence[0].get('text', '')
                    elif isinstance(sentence, dict):
                        return sentence.get('text', '')
                
                # 检查是否有utterances字段
                if 'utterances' in response.payload_msg:
                    utterances = response.payload_msg['utterances']
                    if isinstance(utterances, list) and len(utterances) > 0:
                        return utterances[0].get('text', '')
                
                # 如果是字符串，直接返回
                if isinstance(response.payload_msg, str):
                    return response.payload_msg
                    
        except Exception as e:
            logger.error(f"提取文字时出错: {e}")
            
        return ""
    
    def _is_final_result(self, response: STTResponse) -> bool:
        """判断是否为最终结果"""
        if not response.payload_msg:
            return False
            
        try:
            if isinstance(response.payload_msg, dict):
                # 检查is_final字段
                if 'is_final' in response.payload_msg:
                    return response.payload_msg['is_final']
                
                # 检查result字段中的is_final
                if 'result' in response.payload_msg:
                    result = response.payload_msg['result']
                    if isinstance(result, dict) and 'is_final' in result:
                        return result['is_final']
                        
        except Exception as e:
            logger.error(f"判断最终结果时出错: {e}")
            
        return response.is_last_package
    
    def get_final_result(self) -> str:
        """获取最终识别结果"""
        return self.final_text
    
    def reset(self):
        """重置处理器状态"""
        self.current_text = ""
        self.final_text = ""
        self.is_processing = False


# 添加音频处理工具类
class AudioProcessor:
    """音频处理器"""
    
    @staticmethod
    def judge_wav(data: bytes) -> bool:
        """判断是否为WAV格式"""
        if len(data) < 44:
            return False
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    
    @staticmethod
    def read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
        """读取WAV文件信息"""
        if len(data) < 44:
            raise ValueError("Invalid WAV file: too short")
            
        # Parsing WAV header
        chunk_id = data[:4]
        if chunk_id != b'RIFF':
            raise ValueError("Invalid WAV file: not RIFF format")
            
        format_ = data[8:12]
        if format_ != b'WAVE':
            raise ValueError("Invalid WAV file: not WAVE format")
            
        # Parse fmt subchunk
        audio_format = struct.unpack('<H', data[20:22])[0]
        num_channels = struct.unpack('<H', data[22:24])[0]
        sample_rate = struct.unpack('<I', data[24:28])[0]
        bits_per_sample = struct.unpack('<H', data[34:36])[0]
        
        # Find the data sub-block
        pos = 36
        while pos < len(data) - 8:
            subchunk_id = data[pos:pos+4]
            subchunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
            if subchunk_id == b'data':
                wave_data = data[pos+8:pos+8+subchunk_size]
                return (
                    num_channels,
                    bits_per_sample // 8,
                    sample_rate,
                    subchunk_size // (num_channels * (bits_per_sample // 8)),
                    wave_data
                )
            pos += 8 + subchunk_size
            
        raise ValueError("Invalid WAV file: no data subchunk found")
    
    @staticmethod
    def get_segment_size(content: bytes, segment_duration: int = 200) -> int:
        """计算音频分段大小"""
        try:
            channel_num, samp_width, frame_rate, _, _ = AudioProcessor.read_wav_info(content)[:5]
            size_per_sec = channel_num * samp_width * frame_rate
            segment_size = size_per_sec * segment_duration // 1000
            return segment_size
        except Exception as e:
            logger.error(f"Failed to calculate segment size: {e}")
            raise
    
    @staticmethod
    def split_audio(data: bytes, segment_size: int) -> List[bytes]:
        """分割音频数据"""
        if segment_size <= 0:
            return []
            
        segments = []
        for i in range(0, len(data), segment_size):
            end = i + segment_size
            if end > len(data):
                end = len(data)
            segments.append(data[i:end])
        return segments


class SpeechToTextProcessor:
    """语音转文字处理器"""
    
    def __init__(self):
        self.current_text = ""
        self.final_text = ""
        self.is_processing = False
        
    def process_response(self, response: STTResponse) -> str:
        """处理ASR响应，返回识别的文字"""
        if response.code != 0:
            logger.error(f"ASR错误: {response.payload_msg}")
            return ""
            
        text = self._extract_text(response)
        if not text:
            return ""
            
        # 判断是否为最终结果
        if self._is_final_result(response):
            self.final_text = text
            self.is_processing = False
            return f"最终结果: {text}"
        else:
            # 中间结果
            self.current_text = text
            self.is_processing = True
            return f"识别中: {text}"
    
    def _extract_text(self, response: STTResponse) -> str:
        """提取识别出的文字"""
        if not response.payload_msg:
            return ""
        
        try:
            # 根据不同的响应格式提取文字
            if isinstance(response.payload_msg, dict):
                # 检查是否有result字段
                if 'result' in response.payload_msg:
                    result = response.payload_msg['result']
                    if isinstance(result, dict) and 'text' in result:
                        return result['text']
                    elif isinstance(result, str):
                        return result
                
                # 检查是否有text字段
                if 'text' in response.payload_msg:
                    return response.payload_msg['text']
                
                # 检查是否有sentence字段
                if 'sentence' in response.payload_msg:
                    sentence = response.payload_msg['sentence']
                    if isinstance(sentence, list) and len(sentence) > 0:
                        return sentence[0].get('text', '')
                    elif isinstance(sentence, dict):
                        return sentence.get('text', '')
                
                # 检查是否有utterances字段
                if 'utterances' in response.payload_msg:
                    utterances = response.payload_msg['utterances']
                    if isinstance(utterances, list) and len(utterances) > 0:
                        return utterances[0].get('text', '')
                
                # 如果是字符串，直接返回
                if isinstance(response.payload_msg, str):
                    return response.payload_msg
            
        except Exception as e:
            logger.error(f"提取文字时出错: {e}")
            
        return ""
    
    def _is_final_result(self, response: STTResponse) -> bool:
        """判断是否为最终结果"""
        if not response.payload_msg:
            return False
            
        try:
            if isinstance(response.payload_msg, dict):
                # 检查is_final字段
                if 'is_final' in response.payload_msg:
                    return response.payload_msg['is_final']
                
                # 检查result字段中的is_final
                if 'result' in response.payload_msg:
                    result = response.payload_msg['result']
                    if isinstance(result, dict) and 'is_final' in result:
                        return result['is_final']
                        
        except Exception as e:
            logger.error(f"判断最终结果时出错: {e}")
            
        return response.is_last_package
    
    def get_final_result(self) -> str:
        """获取最终识别结果"""
        return self.final_text
    
    def reset(self):
        """重置处理器状态"""
        self.current_text = ""
        self.final_text = ""
        self.is_processing = False


class MicrophoneRecorder:
    """麦克风录音器"""
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.is_recording = False
        self.audio_buffer = []
        
    async def start_recording(self, stt_client: STTClient):
        """开始录音并实时发送到STT"""
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            self.is_recording = True
            logger.info("开始录音...")
            
            while self.is_recording:
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    await stt_client.send_audio(data)
                    await asyncio.sleep(0.1)  # 100ms间隔
                except Exception as e:
                    logger.error(f"录音错误: {e}")
                    break
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
        except ImportError:
            logger.error("需要安装pyaudio库: pip install pyaudio")
        except Exception as e:
            logger.error(f"启动录音失败: {e}")
    
    def stop_recording(self):
        """停止录音"""
        self.is_recording = False
        logger.info("录音已停止")
    
    def get_audio_buffer(self) -> bytes:
        """获取录音缓冲数据"""
        return b''.join(self.audio_buffer)
    
    def clear_buffer(self):
        """清空录音缓冲"""
        self.audio_buffer.clear()