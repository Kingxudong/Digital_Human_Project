import asyncio
import logging
from typing import Optional, Callable
from datetime import datetime

# 导入我们创建的模块
from audio_capture import AudioCapture
from audio_processor import AudioProcessor
from audio_websocket_client import AudioWebSocketClient

logger = logging.getLogger(__name__)

class RealTimeAudioHandler:
    """
    实时音频处理器 - 整合所有组件
    基于小智项目的设计，实现完整的音频采集、处理、传输流程
    """
    
    def __init__(self, 
                 server_url: str, 
                 session_id: str,
                 sample_rate: int = 16000,
                 channels: int = 1):
        
        self.server_url = server_url
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.channels = channels
        
        # 初始化组件
        self.audio_capture = AudioCapture(sample_rate, channels)
        self.audio_processor = AudioProcessor(sample_rate, sample_rate, channels)
        self.websocket_client = AudioWebSocketClient(server_url, session_id)
        
        # 状态管理
        self.is_processing = False
        self.start_time = None
        
        # 设置回调
        self.audio_capture.on_audio_data = self._on_audio_data
        self.websocket_client.on_stt_result = self._on_stt_result
        self.websocket_client.on_error = self._on_error
        self.websocket_client.on_connected = self._on_connected
        self.websocket_client.on_disconnected = self._on_disconnected
        
        # 用户回调
        self.on_stt_result: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_status_change: Optional[Callable] = None
        
        logger.info(f"实时音频处理器初始化完成 - 会话ID: {session_id}")
        
    async def start(self):
        """开始实时音频处理"""
        if self.is_processing:
            logger.warning("实时音频处理已经在进行中")
            return
            
        try:
            logger.info("开始实时音频处理...")
            
            # 1. 初始化音频采集器
            await self.audio_capture.initialize()
            
            # 2. 连接WebSocket
            await self.websocket_client.connect()
            
            # 3. 开始录音
            await self.audio_capture.start_recording()
            
            self.is_processing = True
            self.start_time = datetime.now()
            
            # 触发状态变化回调
            if self.on_status_change:
                await self.on_status_change("started")
                
            logger.info("实时音频处理已启动")
            
        except Exception as e:
            logger.error(f"启动实时音频处理失败: {e}")
            await self.stop()
            raise
        
    async def stop(self):
        """停止实时音频处理"""
        if not self.is_processing:
            return
            
        try:
            logger.info("停止实时音频处理...")
            
            # 1. 停止录音
            self.audio_capture.stop_recording()
            
            # 2. 断开WebSocket
            await self.websocket_client.disconnect()
            
            self.is_processing = False
            
            # 触发状态变化回调
            if self.on_status_change:
                await self.on_status_change("stopped")
                
            logger.info("实时音频处理已停止")
            
        except Exception as e:
            logger.error(f"停止实时音频处理失败: {e}")
            
    async def _on_audio_data(self, audio_data: bytes):
        """音频数据回调"""
        if not self.is_processing:
            return
            
        try:
            # 处理音频数据
            processed_audio = self.audio_processor.process_audio_chunk(audio_data)
            
            if processed_audio:
                # 发送到WebSocket
                await self.websocket_client.send_audio_data(processed_audio)
                
        except Exception as e:
            logger.error(f"音频数据处理失败: {e}")
            if self.on_error:
                await self.on_error(str(e))
            
    async def _on_stt_result(self, text: str, is_final: bool, confidence: float):
        """STT结果回调"""
        logger.info(f"STT结果: {text} (最终: {is_final}, 置信度: {confidence})")
        
        # 触发用户回调
        if self.on_stt_result:
            await self.on_stt_result(text, is_final, confidence)
            
    async def _on_error(self, error: str):
        """错误回调"""
        logger.error(f"处理错误: {error}")
        
        # 触发用户回调
        if self.on_error:
            await self.on_error(error)
            
    async def _on_connected(self):
        """连接成功回调"""
        logger.info("WebSocket连接成功")
        
    async def _on_disconnected(self):
        """连接断开回调"""
        logger.info("WebSocket连接断开")
        
    def get_statistics(self) -> dict:
        """获取处理统计信息"""
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        return {
            "is_processing": self.is_processing,
            "processing_duration": duration,
            "session_id": self.session_id,
            "server_url": self.server_url,
            "audio_capture_stats": self.audio_capture.get_statistics(),
            "audio_processor_stats": self.audio_processor.get_statistics(),
            "websocket_stats": self.websocket_client.get_statistics()
        }
        
    def reset(self):
        """重置处理器状态"""
        self.audio_capture.reset()
        self.audio_processor.reset()
        logger.info("实时音频处理器状态已重置")