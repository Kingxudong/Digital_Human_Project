import asyncio
import aiohttp
import json
import struct
import gzip
import uuid
import logging
import os
import subprocess
import pyaudio
import wave
import threading
import queue
import time
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator

# Configuring Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('run.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constant Definition
DEFAULT_SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1

class MicrophoneRecorder:
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, chunk_size: int = CHUNK_SIZE):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio = pyaudio.PyAudio()
        self.frames = []
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.stream = None
        
    def start_recording(self):
        """开始录制音频"""
        self.is_recording = True
        self.frames = []
        
        def callback(in_data, frame_count, time_info, status):
            if self.is_recording:
                self.audio_queue.put(in_data)
                return (in_data, pyaudio.paContinue)
            else:
                return (None, pyaudio.paComplete)
        
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=callback
        )
        
        self.stream.start_stream()
        logger.info("开始录制音频...")
        
    def stop_recording(self):
        """停止录制音频"""
        self.is_recording = False
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        logger.info("停止录制音频")
        
    def get_audio_data(self) -> bytes:
        """获取录制的音频数据"""
        # 收集所有音频数据
        while not self.audio_queue.empty():
            self.frames.append(self.audio_queue.get())
            
        # 将音频数据转换为WAV格式
        wav_data = b''
        for frame in self.frames:
            wav_data += frame
            
        # 创建WAV文件头
        wav_header = self._create_wav_header(len(wav_data))
        return wav_header + wav_data
        
    def _create_wav_header(self, data_size: int) -> bytes:
        """创建WAV文件头"""
        # WAV文件头结构
        riff_header = b'RIFF'
        file_size = 36 + data_size
        wave_header = b'WAVE'
        fmt_header = b'fmt '
        fmt_size = 16
        audio_format = 1  # PCM
        num_channels = CHANNELS
        sample_rate = self.sample_rate
        byte_rate = sample_rate * num_channels * 2  # 16位 = 2字节
        block_align = num_channels * 2
        bits_per_sample = 16
        data_header = b'data'
        
        # 构建WAV头
        header = struct.pack('<4sI4s4sIHHIIHH4sI',
            riff_header, file_size, wave_header, fmt_header, fmt_size,
            audio_format, num_channels, sample_rate, byte_rate,
            block_align, bits_per_sample, data_header, data_size
        )
        
        return header
        
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'audio'):
            self.audio.terminate()

class ProtocolVersion:
    V1 = 0b0001

class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111

class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011

class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001

class CompressionType:
    GZIP = 0b0001


class Config:
    def __init__(self):
        # Fill in the app id and access token
        self.auth = {
            "app_key": "5182023671",
            "access_key": "fm8FnSDJJWVlPm3Tq0YWERFtPNefnyAs"
        }

    @property
    def app_key(self) -> str:
        return self.auth["app_key"]

    @property
    def access_key(self) -> str:
        return self.auth["access_key"]

config = Config()

class CommonUtils:
    @staticmethod
    def gzip_compress(data: bytes) -> bytes:
        return gzip.compress(data)

    @staticmethod
    def gzip_decompress(data: bytes) -> bytes:
        return gzip.decompress(data)

    @staticmethod
    def judge_wav(data: bytes) -> bool:
        if len(data) < 44:
            return False
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'

    @staticmethod
    def convert_wav_with_path(audio_path: str, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
        try:
            cmd = [
                "ffmpeg", "-v", "quiet", "-y", "-i", audio_path,
                "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sample_rate),
                "-f", "wav", "-"
            ]
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Try deleting the original file
            try:
                os.remove(audio_path)
            except OSError as e:
                logger.warning(f"Failed to remove original file: {e}")
                
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e.stderr.decode()}")
            raise RuntimeError(f"Audio conversion failed: {e.stderr.decode()}")

    @staticmethod
    def read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
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

class AsrRequestHeader:
    def __init__(self):
        self.message_type = MessageType.CLIENT_FULL_REQUEST
        self.message_type_specific_flags = MessageTypeSpecificFlags.POS_SEQUENCE
        self.serialization_type = SerializationType.JSON
        self.compression_type = CompressionType.GZIP
        self.reserved_data = bytes([0x00])

    def with_message_type(self, message_type: int) -> 'AsrRequestHeader':
        self.message_type = message_type
        return self

    def with_message_type_specific_flags(self, flags: int) -> 'AsrRequestHeader':
        self.message_type_specific_flags = flags
        return self

    def with_serialization_type(self, serialization_type: int) -> 'AsrRequestHeader':
        self.serialization_type = serialization_type
        return self

    def with_compression_type(self, compression_type: int) -> 'AsrRequestHeader':
        self.compression_type = compression_type
        return self

    def with_reserved_data(self, reserved_data: bytes) -> 'AsrRequestHeader':
        self.reserved_data = reserved_data
        return self

    def to_bytes(self) -> bytes:
        header = bytearray()
        header.append((ProtocolVersion.V1 << 4) | 1)
        header.append((self.message_type << 4) | self.message_type_specific_flags)
        header.append((self.serialization_type << 4) | self.compression_type)
        header.extend(self.reserved_data)
        return bytes(header)

    @staticmethod
    def default_header() -> 'AsrRequestHeader':
        return AsrRequestHeader()

class RequestBuilder:
    @staticmethod
    def new_auth_headers() -> Dict[str, str]:
        reqid = str(uuid.uuid4())
        return {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": reqid,
            "X-Api-Access-Key": config.access_key,
            "X-Api-App-Key": config.app_key
        }

    @staticmethod
    def new_full_client_request(seq: int) -> bytes:  # Add seq parameter
        header = AsrRequestHeader.default_header() \
            .with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        
        payload = {
            "user": {
                "uid": "demo_uid"
            },
            "audio": {
                "format": "wav",
                "codec": "raw",
                "rate": 16000,
                "bits": 16,
                "channel": 1
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "enable_nonstream": False
            }
        }
        
        payload_bytes = json.dumps(payload).encode('utf-8')
        compressed_payload = CommonUtils.gzip_compress(payload_bytes)
        payload_size = len(compressed_payload)
        
        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))  # Use the passed seq
        request.extend(struct.pack('>I', payload_size))
        request.extend(compressed_payload)
        
        return bytes(request)

    @staticmethod
    def new_audio_only_request(seq: int, segment: bytes, is_last: bool = False) -> bytes:
        header = AsrRequestHeader.default_header()
        if is_last:  # The last packet is specially processed
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.NEG_WITH_SEQUENCE)
            seq = -seq  # Set to negative value
        else:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        header.with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)
        
        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))
        
        compressed_segment = CommonUtils.gzip_compress(segment)
        request.extend(struct.pack('>I', len(compressed_segment)))
        request.extend(compressed_segment)
        
        return bytes(request)

class AsrResponse:
    def __init__(self):
        self.code = 0
        self.event = 0
        self.is_last_package = False
        self.payload_sequence = 0
        self.payload_size = 0
        self.payload_msg = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "event": self.event,
            "is_last_package": self.is_last_package,
            "payload_sequence": self.payload_sequence,
            "payload_size": self.payload_size,
            "payload_msg": self.payload_msg
        }
    
    def get_text(self) -> str:
        """提取识别出的文字"""
        if not self.payload_msg:
            return ""
        
        try:
            # 根据不同的响应格式提取文字
            if isinstance(self.payload_msg, dict):
                # 检查是否有result字段
                if 'result' in self.payload_msg:
                    result = self.payload_msg['result']
                    if isinstance(result, dict) and 'text' in result:
                        return result['text']
                    elif isinstance(result, str):
                        return result
                
                # 检查是否有text字段
                if 'text' in self.payload_msg:
                    return self.payload_msg['text']
                
                # 检查是否有sentence字段
                if 'sentence' in self.payload_msg:
                    sentence = self.payload_msg['sentence']
                    if isinstance(sentence, list) and len(sentence) > 0:
                        return sentence[0].get('text', '')
                    elif isinstance(sentence, dict):
                        return sentence.get('text', '')
                
                # 检查是否有utterances字段
                if 'utterances' in self.payload_msg:
                    utterances = self.payload_msg['utterances']
                    if isinstance(utterances, list) and len(utterances) > 0:
                        return utterances[0].get('text', '')
                
                # 如果是字符串，直接返回
                if isinstance(self.payload_msg, str):
                    return self.payload_msg
                    
        except Exception as e:
            logger.error(f"提取文字时出错: {e}")
            
        return ""
    
    def is_final_result(self) -> bool:
        """判断是否为最终结果"""
        if not self.payload_msg:
            return False
            
        try:
            if isinstance(self.payload_msg, dict):
                # 检查is_final字段
                if 'is_final' in self.payload_msg:
                    return self.payload_msg['is_final']
                
                # 检查result字段中的is_final
                if 'result' in self.payload_msg:
                    result = self.payload_msg['result']
                    if isinstance(result, dict) and 'is_final' in result:
                        return result['is_final']
                        
        except Exception as e:
            logger.error(f"判断最终结果时出错: {e}")
            
        return self.is_last_package

class SpeechToTextProcessor:
    """语音转文字处理器"""
    
    def __init__(self):
        self.current_text = ""
        self.final_text = ""
        self.is_processing = False
        
    def process_response(self, response: AsrResponse) -> str:
        """处理ASR响应，返回识别的文字"""
        if response.code != 0:
            logger.error(f"ASR错误: {response.payload_msg}")
            return ""
            
        text = response.get_text()
        if not text:
            return ""
            
        # 判断是否为最终结果
        if response.is_final_result():
            self.final_text = text
            self.is_processing = False
            return f"最终结果: {text}"
        else:
            # 中间结果
            self.current_text = text
            self.is_processing = True
            return f"识别中: {text}"
    
    def get_final_result(self) -> str:
        """获取最终识别结果"""
        return self.final_text
    
    def reset(self):
        """重置处理器状态"""
        self.current_text = ""
        self.final_text = ""
        self.is_processing = False

class RealTimeSpeechRecognizer:
    """实时语音识别器"""
    
    def __init__(self, url: str, segment_duration: int = 200):
        self.url = url
        self.segment_duration = segment_duration
        self.recorder = MicrophoneRecorder()
        self.client = None
        self.is_running = False
        
    async def start_real_time_recognition(self):
        """开始实时语音识别"""
        print("🎤 实时语音识别已启动")
        print("📝 使用说明:")
        print("1. 请开始说话，系统会实时显示识别结果")
        print("2. 按 Ctrl+C 停止识别")
        print("-" * 50)
        
        try:
            async with AsrWsClient(self.url, self.segment_duration) as client:
                self.client = client
                self.is_running = True
                
                # 开始录制
                self.recorder.start_recording()
                print("🎙️ 开始录制音频...")
                
                # 使用简化的方法：录制一段时间后处理
                await self._simple_recognition()
                    
        except Exception as e:
            logger.error(f"实时语音识别失败: {e}")
            print(f"❌ 错误: {e}")
        finally:
            self.is_running = False
            self.recorder.stop_recording()
    
    async def _simple_recognition(self):
        """简化的识别方法"""
        try:
            # 录制3秒音频
            print("请说话（3秒后自动停止）...")
            await asyncio.sleep(3)
            
            # 停止录制
            self.recorder.stop_recording()
            print("停止录制音频")
            
            # 获取录制的音频数据
            audio_data = self.recorder.get_audio_data()
            print(f"录制音频大小: {len(audio_data)} 字节")
            
            if len(audio_data) < 1000:  # 音频太短
                print("⚠️ 录制的音频太短，请重新尝试")
                return
            
            # 直接处理音频数据
            await self._process_audio_data(audio_data)
                    
        except Exception as e:
            logger.error(f"简化识别失败: {e}")
            raise
    
    async def _process_audio_data(self, audio_data: bytes):
        """处理音频数据"""
        try:
            # 创建连接
            await self.client.create_connection()
            
            # 发送初始请求
            await self.client.send_full_client_request()
            
            # 计算分块大小
            segment_size = self.client.get_segment_size(audio_data)
            
            # 开始音频流处理
            async for response in self.client.start_audio_stream(segment_size, audio_data):
                # 处理响应并显示文字
                text_result = self.client.stt_processor.process_response(response)
                if text_result:
                    print(f"\n🎤 {text_result}")
                    
        except Exception as e:
            logger.error(f"处理音频数据失败: {e}")
            raise

class ResponseParser:
    @staticmethod
    def parse_response(msg: bytes) -> AsrResponse:
        response = AsrResponse()
        
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
        if message_type == MessageType.SERVER_FULL_RESPONSE:
            response.payload_size = struct.unpack('>I', payload[:4])[0]
            payload = payload[4:]
        elif message_type == MessageType.SERVER_ERROR_RESPONSE:
            response.code = struct.unpack('>i', payload[:4])[0]
            response.payload_size = struct.unpack('>I', payload[4:8])[0]
            payload = payload[8:]
            
        if not payload:
            return response
            
        # Decompress payload
        if message_compression == CompressionType.GZIP:
            try:
                payload = CommonUtils.gzip_decompress(payload)
            except Exception as e:
                logger.error(f"Failed to decompress payload: {e}")
                return response
                
        # Parsing the Payload
        try:
            if serialization_method == SerializationType.JSON:
                response.payload_msg = json.loads(payload.decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to parse payload: {e}")
            
        return response

class AsrWsClient:
    def __init__(self, url: str, segment_duration: int = 200):
        self.seq = 1
        self.url = url
        self.segment_duration = segment_duration
        self.conn = None
        self.session = None  # Add session reference
        self.stt_processor = SpeechToTextProcessor()  # 语音转文字处理器

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        if self.conn and not self.conn.closed:
            await self.conn.close()
        if self.session and not self.session.closed:
            await self.session.close()
        
    async def read_audio_data(self, file_path: str = None, recorder: MicrophoneRecorder = None) -> bytes:
        try:
            if recorder:
                # 使用麦克风录制 - 由前端控制开始和结束
                logger.info("使用麦克风录制音频...")
                logger.info("录音由前端控制开始和结束，无需自动停止")
                recorder.start_recording()
              
                
                
                return b""  # 返回空数据，实际使用时应通过API获取
            else:
                # 使用文件输入
                with open(file_path, 'rb') as f:
                    content = f.read()
                    
                if not CommonUtils.judge_wav(content):
                    logger.info("Converting audio to WAV format...")
                    content = CommonUtils.convert_wav_with_path(file_path, DEFAULT_SAMPLE_RATE)
                    
                return content
        except Exception as e:
            logger.error(f"Failed to read audio data: {e}")
            raise
            
    def get_segment_size(self, content: bytes) -> int:
        try:
            channel_num, samp_width, frame_rate, _, _ = CommonUtils.read_wav_info(content)[:5]
            size_per_sec = channel_num * samp_width * frame_rate
            segment_size = size_per_sec * self.segment_duration // 1000
            return segment_size
        except Exception as e:
            logger.error(f"Failed to calculate segment size: {e}")
            raise
            
    async def create_connection(self) -> None:
        headers = RequestBuilder.new_auth_headers()
        try:
            self.conn = await self.session.ws_connect(  # Use self.session
                self.url,
                headers=headers
            )
            logger.info(f"Connected to {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise
            
    async def send_full_client_request(self) -> None:
        request = RequestBuilder.new_full_client_request(self.seq)
        self.seq += 1  # Increment after sending
        try:
            await self.conn.send_bytes(request)
            logger.info(f"Sent full client request with seq: {self.seq-1}")
            
            msg = await self.conn.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                response = ResponseParser.parse_response(msg.data)
                logger.info(f"Received response: {response.to_dict()}")
            else:
                logger.error(f"Unexpected message type: {msg.type}")
        except Exception as e:
            logger.error(f"Failed to send full client request: {e}")
            raise
            
    async def send_messages(self, segment_size: int, content: bytes) -> AsyncGenerator[None, None]:
        audio_segments = self.split_audio(content, segment_size)
        total_segments = len(audio_segments)
        
        logger.info(f"开始发送音频数据，共 {total_segments} 个片段")
        
        for i, segment in enumerate(audio_segments):
            is_last = (i == total_segments - 1)
            request = RequestBuilder.new_audio_only_request(
                self.seq, 
                segment,
                is_last=is_last
            )
            await self.conn.send_bytes(request)
            logger.info(f"Sent audio segment with seq: {self.seq} (last: {is_last}, size: {len(segment)})")
            
            if not is_last:
                self.seq += 1
                
            # 减少发送间隔，避免超时
            await asyncio.sleep(0.05)  # 50ms间隔
            # Give up control and allow messages to be received
            yield
            
    async def recv_messages(self) -> AsyncGenerator[AsrResponse, None]:
        try:
            async for msg in self.conn:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    response = ResponseParser.parse_response(msg.data)
                    yield response
                    
                    if response.is_last_package or response.code != 0:
                        break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed")
                    break
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
            raise
            
    async def start_audio_stream(self, segment_size: int, content: bytes) -> AsyncGenerator[AsrResponse, None]:
        async def sender():
            async for _ in self.send_messages(segment_size, content):
                pass
                
        # Start sending and receiving tasks
        sender_task = asyncio.create_task(sender())
        
        try:
            async for response in self.recv_messages():
                yield response
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass
                
    @staticmethod
    def split_audio(data: bytes, segment_size: int) -> List[bytes]:
        if segment_size <= 0:
            return []
            
        segments = []
        for i in range(0, len(data), segment_size):
            end = i + segment_size
            if end > len(data):
                end = len(data)
            segments.append(data[i:end])
        return segments
        
    async def execute(self, file_path: str = None, recorder: MicrophoneRecorder = None, verbose: bool = False) -> AsyncGenerator[AsrResponse, None]:
        if not file_path and not recorder:
            raise ValueError("必须提供文件路径或麦克风录制器")
            
        if not self.url:
            raise ValueError("URL is empty")
            
        self.seq = 1
        self.stt_processor.reset()  # 重置处理器状态
        
        try:
            # 1. Reading Audio Files or Recording from Microphone
            content = await self.read_audio_data(file_path, recorder)
            
            # 2. Calculating segment size
            segment_size = self.get_segment_size(content)
            
            # 3. Creating a WebSocket Connection
            await self.create_connection()
            
            # 4. Sending a full client request
            await self.send_full_client_request()
            
            # 5. Start audio streaming
            async for response in self.start_audio_stream(segment_size, content):
                # 处理语音转文字
                text_result = self.stt_processor.process_response(response)
                if text_result:
                    print(f"\n🎤 {text_result}")
                
                # 如果启用详细输出，显示完整的响应信息
                if verbose:
                    logger.info(f"详细响应: {json.dumps(response.to_dict(), indent=2, ensure_ascii=False)}")
                
                yield response
                
        except Exception as e:
            logger.error(f"Error in ASR execution: {e}")
            raise
        finally:
            if self.conn:
                await self.conn.close()

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="ASR WebSocket Client")
    parser.add_argument("--file", type=str, help="Audio file path")
    parser.add_argument("--mic", action="store_true", help="使用麦克风输入")
    parser.add_argument("--realtime", action="store_true", help="实时语音识别模式")
    parser.add_argument("--verbose", action="store_true", help="显示详细的响应信息")

    #url = "wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel"
    #url = "wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel_nostream"
    parser.add_argument("--url", type=str, default="wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel", 
                       help="WebSocket URL")
    parser.add_argument("--seg-duration", type=int, default=200, 
                       help="Audio duration(ms) per packet, default:200")
    
    args = parser.parse_args()
    
    # 验证参数
    if not args.file and not args.mic and not args.realtime:
        parser.error("必须提供 --file、--mic 或 --realtime 参数")
    
    if sum([bool(args.file), bool(args.mic), bool(args.realtime)]) > 1:
        parser.error("不能同时使用多个输入模式参数")
    
    async with AsrWsClient(args.url, args.seg_duration) as client:  # use async with
        try:
            if args.realtime:
                # 实时语音识别模式
                print("🎤 启动实时语音识别...")
                recognizer = RealTimeSpeechRecognizer(args.url, args.seg_duration)
                await recognizer.start_real_time_recognition()
            elif args.mic:
                # 使用麦克风输入
                print("🎙️  开始语音识别...")
                recorder = MicrophoneRecorder()
                async for response in client.execute(recorder=recorder, verbose=args.verbose):
                    # 语音转文字的结果已经在execute方法中打印了
                    pass
                print("\n✅ 语音识别完成！")
            else:
                # 使用文件输入
                print("📁 开始处理音频文件...")
                async for response in client.execute(file_path=args.file, verbose=args.verbose):
                    # 语音转文字的结果已经在execute方法中打印了
                    pass
                print("\n✅ 音频文件处理完成！")
        except Exception as e:
            logger.error(f"ASR processing failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())

   