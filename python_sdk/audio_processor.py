import asyncio
import numpy as np
import opuslib
import soxr
from collections import deque
from typing import Optional, Tuple, Dict, Any, List
import logging
import time
from dataclasses import dataclass
from enum import Enum

from audio_config import AudioConfig

logger = logging.getLogger(__name__)

class ProcessingState(Enum):
    """处理状态枚举"""
    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"
    CLOSED = "closed"

@dataclass
class ProcessingStatistics:
    """处理统计信息"""
    total_input_samples: int = 0
    total_output_bytes: int = 0
    total_frames_processed: int = 0
    processing_time: float = 0.0
    compression_ratio: float = 0.0
    input_buffer_size: int = 0
    output_buffer_size: int = 0
    error_count: int = 0
    resampling_count: int = 0
    encoding_count: int = 0

class AudioProcessor:
    """
    改进的音频处理器 - 基于小智项目的设计
    负责音频重采样、Opus编码、质量监控
    增强功能：状态管理、错误恢复、性能优化、质量检测
    """
    
    def __init__(self, 
                 input_sample_rate: int = AudioConfig.INPUT_SAMPLE_RATE,
                 output_sample_rate: int = AudioConfig.OUTPUT_SAMPLE_RATE,
                 channels: int = AudioConfig.CHANNELS,
                 frame_duration_ms: int = AudioConfig.FRAME_DURATION,
                 bitrate: int = 64000,
                 complexity: int = 5):
        
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.bitrate = bitrate
        self.complexity = complexity
        
        # 计算帧大小
        self.input_frame_size = int(input_sample_rate * frame_duration_ms / 1000)
        self.output_frame_size = int(output_sample_rate * frame_duration_ms / 1000)
        
        # 状态管理
        self.state = ProcessingState.IDLE
        self._error_count = 0
        self._max_errors = 10
        
        # 初始化组件
        self._init_resampler()
        self._init_encoder()
        
        # 缓冲区
        self.input_buffer = deque()
        self.resample_buffer = deque()
        self.output_buffer = deque(maxlen=100)
        
        # 统计信息
        self.stats = ProcessingStatistics()
        self.processing_start_time = None
        
        # 回调函数
        self.on_processed_audio: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None
        
        # 性能监控
        self._last_stats_time = time.time()
        self._stats_interval = 5.0  # 5秒统计一次
        
        # 质量监控
        self._quality_threshold = 0.8  # 质量阈值
        self._last_quality_check = time.time()
        self._quality_check_interval = 10.0  # 10秒检查一次质量
        
        logger.info(f"音频处理器初始化完成 - 输入采样率: {input_sample_rate}Hz, "
                   f"输出采样率: {output_sample_rate}Hz, 帧大小: {self.output_frame_size}, "
                   f"比特率: {bitrate}bps, 复杂度: {complexity}")
        
    def _init_resampler(self):
        """初始化重采样器"""
        try:
            if self.input_sample_rate != self.output_sample_rate:
                self.resampler = soxr.ResampleStream(
                    self.input_sample_rate,
                    self.output_sample_rate,
                    self.channels,
                    dtype=np.int16
                )
                self.needs_resampling = True
                logger.info(f"启用重采样: {self.input_sample_rate}Hz -> {self.output_sample_rate}Hz")
            else:
                self.needs_resampling = False
                logger.info("无需重采样")
                
        except Exception as e:
            logger.error(f"重采样器初始化失败: {e}")
            self.needs_resampling = False
            
    def _init_encoder(self):
        """初始化Opus编码器"""
        try:
            self.encoder = opuslib.Encoder(
                self.output_sample_rate,
                self.channels,
                opuslib.APPLICATION_AUDIO
            )
            
            # 优化编码参数
            self.encoder.bitrate = self.bitrate
            self.encoder.complexity = self.complexity
            self.encoder.signal = opuslib.SIGNAL_VOICE
            self.encoder.lsb_depth = 16
            
            logger.info(f"Opus编码器初始化完成 - 比特率: {self.bitrate}bps, 复杂度: {self.complexity}")
            
        except Exception as e:
            logger.error(f"Opus编码器初始化失败: {e}")
            raise
        
    def process_audio_chunk(self, audio_chunk: bytes) -> Optional[bytes]:
        """处理音频块 - 实时处理"""
        try:
            if self.state == ProcessingState.ERROR:
                logger.warning("处理器处于错误状态，跳过处理")
                return None
                
            if self.processing_start_time is None:
                self.processing_start_time = time.time()
                self.state = ProcessingState.PROCESSING
            
            # 1. 转换为numpy数组
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            self.stats.total_input_samples += len(audio_array)
            
            # 2. 添加到输入缓冲区
            self.input_buffer.append(audio_array)
            
            # 3. 检查是否有足够数据进行处理
            if self._has_enough_data():
                result = self._process_buffered_audio()
                
                # 质量检查
                self._check_quality()
                
                # 性能统计
                self._update_performance_stats()
                
                return result
                
        except Exception as e:
            self.stats.error_count += 1
            logger.error(f"音频处理错误: {e}")
            
            if self.stats.error_count >= self._max_errors:
                self.state = ProcessingState.ERROR
                logger.error("错误次数过多，处理器进入错误状态")
                
            if self.on_error:
                asyncio.create_task(self._call_error_callback(str(e)))
            
        return None
        
    def _has_enough_data(self) -> bool:
        """检查是否有足够的数据进行处理"""
        total_samples = sum(len(arr) for arr in self.input_buffer)
        return total_samples >= self.input_frame_size * 2  # 2倍帧大小作为缓冲
        
    def _process_buffered_audio(self) -> bytes:
        """处理缓冲的音频数据"""
        try:
            # 1. 合并音频数据
            combined_audio = np.concatenate(list(self.input_buffer))
            self.input_buffer.clear()
            
            # 2. 重采样
            if self.needs_resampling:
                resampled_audio = self._resample_audio(combined_audio)
                self.stats.resampling_count += 1
            else:
                resampled_audio = combined_audio
                
            # 3. 分帧编码
            encoded_data = self._encode_frames(resampled_audio)
            self.stats.encoding_count += 1
            
            # 4. 更新统计
            self.stats.total_output_bytes += len(encoded_data)
            
            return encoded_data
            
        except Exception as e:
            logger.error(f"缓冲音频处理失败: {e}")
            return b''
        
    def _resample_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """重采样音频数据"""
        try:
            if self.needs_resampling and self.resampler:
                resampled_data = self.resampler.resample(audio_data)
                return resampled_data
            else:
                return audio_data
                
        except Exception as e:
            logger.error(f"重采样失败: {e}")
            return audio_data
        
    def _encode_frames(self, audio_data: np.ndarray) -> bytes:
        """分帧编码音频数据"""
        encoded_frames = []
        
        try:
            # 分帧处理
            for i in range(0, len(audio_data), self.output_frame_size):
                frame = audio_data[i:i + self.output_frame_size]
                
                # 填充最后一帧
                if len(frame) < self.output_frame_size:
                    frame = np.pad(frame, (0, self.output_frame_size - len(frame)), 'constant')
                    
                # 编码帧
                frame_bytes = frame.tobytes()
                encoded_frame = self.encoder.encode(frame_bytes, self.output_frame_size)
                encoded_frames.append(encoded_frame)
                self.stats.total_frames_processed += 1
                
        except Exception as e:
            logger.error(f"帧编码失败: {e}")
            
        return b''.join(encoded_frames)
        
    def process_audio_file(self, audio_data: bytes) -> bytes:
        """处理完整音频文件"""
        try:
            # 转换为numpy数组
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # 重采样
            if self.needs_resampling:
                resampled_audio = self._resample_audio(audio_array)
            else:
                resampled_audio = audio_array
                
            # 编码
            encoded_data = self._encode_frames(resampled_audio)
            
            return encoded_data
            
        except Exception as e:
            logger.error(f"音频文件处理失败: {e}")
            return b''
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        current_time = time.time()
        processing_time = current_time - self.processing_start_time if self.processing_start_time else 0
        
        # 计算压缩比
        input_bytes = self.stats.total_input_samples * 2  # 16bit = 2字节
        compression_ratio = (self.stats.total_output_bytes / input_bytes) if input_bytes > 0 else 0
        self.stats.compression_ratio = compression_ratio
        self.stats.processing_time = processing_time
        
        return {
            "state": self.state.value,
            "input_samples": self.stats.total_input_samples,
            "output_bytes": self.stats.total_output_bytes,
            "frames_processed": self.stats.total_frames_processed,
            "compression_ratio": compression_ratio,
            "processing_time": processing_time,
            "input_buffer_size": len(self.input_buffer),
            "output_buffer_size": len(self.output_buffer),
            "error_count": self.stats.error_count,
            "resampling_count": self.stats.resampling_count,
            "encoding_count": self.stats.encoding_count,
            "input_frame_size": self.input_frame_size,
            "output_frame_size": self.output_frame_size,
            "needs_resampling": self.needs_resampling,
            "input_sample_rate": self.input_sample_rate,
            "output_sample_rate": self.output_sample_rate,
            "bitrate": self.bitrate,
            "complexity": self.complexity
        }
        
    def reset(self):
        """重置处理器状态"""
        self.input_buffer.clear()
        self.resample_buffer.clear()
        self.output_buffer.clear()
        self.stats = ProcessingStatistics()
        self.processing_start_time = None
        self.state = ProcessingState.IDLE
        self._error_count = 0
        logger.info("音频处理器状态已重置")
        
    def _check_quality(self):
        """检查音频质量"""
        current_time = time.time()
        if current_time - self._last_quality_check >= self._quality_check_interval:
            self._last_quality_check = current_time
            
            # 检查压缩比
            if self.stats.compression_ratio > 0:
                quality_score = min(1.0, self.stats.compression_ratio / 0.1)  # 压缩比越高质量越好
                
                if quality_score < self._quality_threshold:
                    logger.warning(f"音频质量较低: {quality_score:.2f}")
                    
    def _update_performance_stats(self):
        """更新性能统计"""
        current_time = time.time()
        if current_time - self._last_stats_time >= self._stats_interval:
            self._last_stats_time = current_time
            
            # 计算性能指标
            if self.stats.processing_time > 0:
                samples_per_second = self.stats.total_input_samples / self.stats.processing_time
                bytes_per_second = self.stats.total_output_bytes / self.stats.processing_time
                
                logger.debug(f"性能统计 - 处理率: {samples_per_second:.0f}/s, "
                           f"输出率: {bytes_per_second/1024:.1f}KB/s, "
                           f"错误数: {self.stats.error_count}")
                           
    async def _call_error_callback(self, error: str):
        """调用错误回调"""
        try:
            if self.on_error:
                await self.on_error(error)
        except Exception as e:
            logger.error(f"错误回调执行失败: {e}")
            
    def get_quality_score(self) -> float:
        """获取音频质量评分"""
        if self.stats.compression_ratio > 0:
            return min(1.0, self.stats.compression_ratio / 0.1)
        return 0.0
        
    def is_healthy(self) -> bool:
        """检查处理器是否健康"""
        return (self.state != ProcessingState.ERROR and 
                self.stats.error_count < self._max_errors)
        
    def close(self):
        """关闭处理器"""
        try:
            self.reset()
            self.state = ProcessingState.CLOSED
            logger.info("音频处理器已关闭")
        except Exception as e:
            logger.error(f"关闭音频处理器失败: {e}")
            
    def __del__(self):
        """析构函数"""
        self.close()