import asyncio
import time
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

from audio_capture import AudioCapture, AudioState
from audio_processor import AudioProcessor, ProcessingState
from audio_websocket_client import AudioWebSocketClient, WebSocketState

logger = logging.getLogger(__name__)

class SystemState(Enum):
    """系统状态枚举"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    CLOSED = "closed"

@dataclass
class SystemStatistics:
    """系统统计信息"""
    total_audio_frames: int = 0
    total_processed_frames: int = 0
    total_transmitted_frames: int = 0
    total_stt_results: int = 0
    system_uptime: float = 0.0
    audio_quality_score: float = 0.0
    transmission_latency: float = 0.0
    error_count: int = 0

class RealtimeAudioSystem:
    """
    实时音频传输系统 - 集成音频采集、处理和WebSocket传输
    基于小智项目的设计理念，实现端到端的实时音频处理
    """
    
    def __init__(self, 
                 websocket_url: str = "ws://localhost:9002/audio",
                 session_id: Optional[str] = None,
                 auto_reconnect: bool = True,
                 enable_audio_processing: bool = True,
                 enable_transmission: bool = True):
        
        self.websocket_url = websocket_url
        self.session_id = session_id
        self.auto_reconnect = auto_reconnect
        self.enable_audio_processing = enable_audio_processing
        self.enable_transmission = enable_transmission
        
        # 系统状态
        self.state = SystemState.IDLE
        self._is_closing = False
        self.start_time = None
        
        # 组件实例
        self.audio_capture = None
        self.audio_processor = None
        self.websocket_client = None
        
        # 统计信息
        self.stats = SystemStatistics()
        
        # 回调函数
        self.on_system_state_change: Optional[Callable] = None
        self.on_stt_result: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_audio_quality_change: Optional[Callable] = None
        
        # 任务管理
        self._main_task = None
        self._monitor_task = None
        
        # 配置
        self._transmission_buffer_size = 10  # 传输缓冲区大小
        self._quality_check_interval = 5.0   # 质量检查间隔
        self._last_quality_check = time.time()
        
        logger.info(f"实时音频系统初始化完成 - WebSocket: {websocket_url}")
        
    async def initialize(self):
        """初始化系统"""
        try:
            await self._set_state(SystemState.INITIALIZING)
            
            logger.info("开始初始化实时音频系统...")
            
            # 1. 初始化音频采集器
            self.audio_capture = AudioCapture(
                sample_rate=16000,
                channels=1,
                frame_duration_ms=20,
                buffer_size=1000,
                silence_threshold=0.005
            )
            
            # 设置音频采集回调
            self.audio_capture.on_audio_data = self._on_audio_data
            self.audio_capture.on_state_change = self._on_capture_state_change
            self.audio_capture.on_silence_detected = self._on_silence_detected
            
            await self.audio_capture.initialize()
            logger.info("音频采集器初始化完成")
            
            # 2. 初始化音频处理器（如果启用）
            if self.enable_audio_processing:
                self.audio_processor = AudioProcessor(
                    input_sample_rate=16000,
                    output_sample_rate=16000,
                    channels=1,
                    frame_duration_ms=20,
                    bitrate=64000,
                    complexity=5
                )
                
                # 设置处理器回调
                self.audio_processor.on_processed_audio = self._on_processed_audio
                self.audio_processor.on_error = self._on_processor_error
                
                logger.info("音频处理器初始化完成")
            
            # 3. 初始化WebSocket客户端（如果启用）
            if self.enable_transmission:
                self.websocket_client = AudioWebSocketClient(
                    server_url=self.websocket_url,
                    session_id=self.session_id,
                    auto_reconnect=self.auto_reconnect,
                    reconnect_interval=5.0,
                    max_reconnect_attempts=10,
                    heartbeat_interval=30.0
                )
                
                # 设置WebSocket回调
                self.websocket_client.on_connected = self._on_websocket_connected
                self.websocket_client.on_disconnected = self._on_websocket_disconnected
                self.websocket_client.on_stt_result = self._on_stt_result
                self.websocket_client.on_error = self._on_websocket_error
                
                logger.info("WebSocket客户端初始化完成")
            
            await self._set_state(SystemState.IDLE)
            logger.info("实时音频系统初始化完成")
            
        except Exception as e:
            await self._set_state(SystemState.ERROR)
            logger.error(f"系统初始化失败: {e}")
            raise
            
    async def start(self):
        """启动系统"""
        if self.state == SystemState.RUNNING:
            logger.warning("系统已在运行中")
            return
            
        try:
            await self._set_state(SystemState.INITIALIZING)
            
            logger.info("启动实时音频系统...")
            self.start_time = time.time()
            self._is_closing = False
            
            # 启动音频采集
            await self.audio_capture.start_recording()
            
            # 连接WebSocket（如果启用）
            if self.enable_transmission and self.websocket_client:
                await self.websocket_client.connect()
            
            # 启动监控任务
            self._monitor_task = asyncio.create_task(self._monitor_system())
            
            await self._set_state(SystemState.RUNNING)
            logger.info("实时音频系统启动完成")
            
        except Exception as e:
            await self._set_state(SystemState.ERROR)
            logger.error(f"系统启动失败: {e}")
            raise
            
    async def stop(self):
        """停止系统"""
        if self.state not in [SystemState.RUNNING, SystemState.PAUSED]:
            logger.warning("系统未在运行中")
            return
            
        logger.info("停止实时音频系统...")
        self._is_closing = True
        
        # 停止音频采集
        if self.audio_capture:
            self.audio_capture.stop_recording()
        
        # 断开WebSocket连接
        if self.websocket_client:
            await self.websocket_client.disconnect()
        
        # 取消监控任务
        if self._monitor_task:
            self._monitor_task.cancel()
        
        # 更新统计信息
        if self.start_time:
            self.stats.system_uptime = time.time() - self.start_time
        
        await self._set_state(SystemState.IDLE)
        logger.info("实时音频系统已停止")
        
    async def pause(self):
        """暂停系统"""
        if self.state == SystemState.RUNNING:
            if self.audio_capture:
                self.audio_capture.pause_recording()
            await self._set_state(SystemState.PAUSED)
            logger.info("系统已暂停")
            
    async def resume(self):
        """恢复系统"""
        if self.state == SystemState.PAUSED:
            if self.audio_capture:
                self.audio_capture.resume_recording()
            await self._set_state(SystemState.RUNNING)
            logger.info("系统已恢复")
            
    async def _on_audio_data(self, audio_data: bytes):
        """音频数据回调"""
        try:
            self.stats.total_audio_frames += 1
            
            # 音频处理
            if self.enable_audio_processing and self.audio_processor:
                processed_data = self.audio_processor.process_audio_chunk(audio_data)
                if processed_data:
                    self.stats.total_processed_frames += 1
                    await self._transmit_audio_data(processed_data)
            else:
                # 直接传输原始音频数据
                await self._transmit_audio_data(audio_data)
                
        except Exception as e:
            logger.error(f"音频数据处理失败: {e}")
            self.stats.error_count += 1
            
    async def _on_processed_audio(self, processed_data: bytes):
        """处理后的音频回调"""
        try:
            await self._transmit_audio_data(processed_data)
        except Exception as e:
            logger.error(f"传输处理后的音频失败: {e}")
            self.stats.error_count += 1
            
    async def _transmit_audio_data(self, audio_data: bytes):
        """传输音频数据"""
        if not self.enable_transmission or not self.websocket_client:
            return
            
        try:
            if self.websocket_client.is_connected():
                # 构建元数据
                metadata = {
                    "timestamp": time.time(),
                    "frame_count": self.stats.total_audio_frames,
                    "audio_level": self.audio_capture.get_audio_level() if self.audio_capture else 0.0,
                    "is_silent": self.audio_capture.is_silent() if self.audio_capture else False
                }
                
                # 发送音频数据
                success = await self.websocket_client.send_audio_data(audio_data, metadata)
                if success:
                    self.stats.total_transmitted_frames += 1
                    
                    # 计算传输延迟
                    websocket_stats = self.websocket_client.get_statistics()
                    self.stats.transmission_latency = websocket_stats.get("latency_ms", 0.0)
                    
        except Exception as e:
            logger.error(f"音频数据传输失败: {e}")
            self.stats.error_count += 1
            
    async def _on_capture_state_change(self, old_state: AudioState, new_state: AudioState):
        """音频采集状态变化回调"""
        logger.info(f"音频采集状态变化: {old_state.value} -> {new_state.value}")
        
        if new_state == AudioState.ERROR:
            await self._handle_error("音频采集器错误")
            
    async def _on_silence_detected(self, silence_duration: float):
        """静音检测回调"""
        logger.info(f"检测到静音: {silence_duration:.2f}秒")
        
        # 可以在这里发送静音事件到服务器
        if self.enable_transmission and self.websocket_client and self.websocket_client.is_connected():
            await self.websocket_client.send_text_message("silence_detected", {
                "duration": silence_duration,
                "timestamp": time.time()
            })
            
    async def _on_processor_error(self, error: str):
        """处理器错误回调"""
        logger.error(f"音频处理器错误: {error}")
        await self._handle_error(f"音频处理器错误: {error}")
        
    async def _on_websocket_connected(self):
        """WebSocket连接回调"""
        logger.info("WebSocket连接成功")
        
        # 发送系统信息
        await self.websocket_client.send_text_message("system_info", {
            "client_type": "realtime_audio_system",
            "capabilities": ["audio_transmission", "stt_reception", "silence_detection"],
            "audio_config": {
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration_ms": 20,
                "encoding": "opus" if self.enable_audio_processing else "pcm"
            }
        })
        
    async def _on_websocket_disconnected(self):
        """WebSocket断开回调"""
        logger.info("WebSocket连接断开")
        
    async def _on_stt_result(self, stt_result: Dict):
        """STT结果回调"""
        try:
            self.stats.total_stt_results += 1
            
            text = stt_result.get("text", "")
            is_final = stt_result.get("is_final", False)
            confidence = stt_result.get("confidence", 0.0)
            
            logger.info(f"STT结果: {text} (最终: {is_final}, 置信度: {confidence:.2f})")
            
            if self.on_stt_result:
                await self.on_stt_result(text, is_final, confidence)
                
        except Exception as e:
            logger.error(f"处理STT结果失败: {e}")
            
    async def _on_websocket_error(self, error: str):
        """WebSocket错误回调"""
        logger.error(f"WebSocket错误: {error}")
        await self._handle_error(f"WebSocket错误: {error}")
        
    async def _handle_error(self, error: str):
        """统一错误处理"""
        self.stats.error_count += 1
        logger.error(f"系统错误: {error}")
        
        if self.on_error:
            await self.on_error(error)
            
    async def _monitor_system(self):
        """系统监控任务"""
        while not self._is_closing:
            try:
                await asyncio.sleep(1)
                
                # 更新系统运行时间
                if self.start_time:
                    self.stats.system_uptime = time.time() - self.start_time
                
                # 质量检查
                current_time = time.time()
                if current_time - self._last_quality_check >= self._quality_check_interval:
                    self._last_quality_check = current_time
                    await self._check_system_quality()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"系统监控错误: {e}")
                
    async def _check_system_quality(self):
        """检查系统质量"""
        try:
            # 计算音频质量评分
            if self.audio_processor:
                quality_score = self.audio_processor.get_quality_score()
                self.stats.audio_quality_score = quality_score
                
                # 质量变化回调
                if self.on_audio_quality_change:
                    await self.on_audio_quality_change(quality_score)
                    
            # 检查系统健康状态
            capture_healthy = (self.audio_capture and 
                             self.audio_capture.state != AudioState.ERROR)
            
            processor_healthy = (not self.audio_processor or 
                               self.audio_processor.is_healthy())
            
            websocket_healthy = (not self.websocket_client or 
                               self.websocket_client.is_healthy())
            
            if not (capture_healthy and processor_healthy and websocket_healthy):
                logger.warning("系统健康状态异常")
                
        except Exception as e:
            logger.error(f"质量检查失败: {e}")
            
    async def _set_state(self, state: SystemState):
        """设置系统状态"""
        old_state = self.state
        self.state = state
        
        if old_state != state:
            logger.info(f"系统状态变化: {old_state.value} -> {state.value}")
            
            if self.on_system_state_change:
                await self.on_system_state_change(old_state, state)
                
    def get_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        # 更新运行时间
        if self.start_time:
            self.stats.system_uptime = time.time() - self.start_time
            
        base_stats = {
            "state": self.state.value,
            "session_id": self.session_id,
            "websocket_url": self.websocket_url,
            "enable_audio_processing": self.enable_audio_processing,
            "enable_transmission": self.enable_transmission,
            "system_uptime": self.stats.system_uptime,
            "total_audio_frames": self.stats.total_audio_frames,
            "total_processed_frames": self.stats.total_processed_frames,
            "total_transmitted_frames": self.stats.total_transmitted_frames,
            "total_stt_results": self.stats.total_stt_results,
            "audio_quality_score": self.stats.audio_quality_score,
            "transmission_latency": self.stats.transmission_latency,
            "error_count": self.stats.error_count
        }
        
        # 添加组件统计
        if self.audio_capture:
            base_stats["audio_capture"] = self.audio_capture.get_statistics()
            
        if self.audio_processor:
            base_stats["audio_processor"] = self.audio_processor.get_statistics()
            
        if self.websocket_client:
            base_stats["websocket_client"] = self.websocket_client.get_statistics()
            
        return base_stats
        
    def is_healthy(self) -> bool:
        """检查系统健康状态"""
        if self.state == SystemState.ERROR:
            return False
            
        # 检查各组件健康状态
        capture_healthy = (self.audio_capture and 
                         self.audio_capture.state != AudioState.ERROR)
        
        processor_healthy = (not self.audio_processor or 
                           self.audio_processor.is_healthy())
        
        websocket_healthy = (not self.websocket_client or 
                           self.websocket_client.is_healthy())
        
        return capture_healthy and processor_healthy and websocket_healthy
        
    async def close(self):
        """关闭系统"""
        await self.stop()
        
        # 关闭组件
        if self.audio_capture:
            self.audio_capture.close()
            
        if self.audio_processor:
            self.audio_processor.close()
            
        if self.websocket_client:
            await self.websocket_client.close()
            
        await self._set_state(SystemState.CLOSED)
        logger.info("实时音频系统已关闭")
        
    def __del__(self):
        """析构函数"""
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self.close())
