import asyncio
import numpy as np
import sounddevice as sd
from collections import deque
from typing import Optional, Callable, Dict, Any, List
import logging
import time
import threading
import traceback
from dataclasses import dataclass
from enum import Enum

from audio_config import AudioConfig

logger = logging.getLogger(__name__)

class AudioState(Enum):
    """音频状态枚举"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RECORDING = "recording"
    PAUSED = "paused"
    ERROR = "error"
    CLOSED = "closed"

@dataclass
class AudioStatistics:
    """音频统计信息"""
    total_samples: int = 0
    total_bytes: int = 0
    duration_seconds: float = 0.0
    last_audio_time: float = 0.0
    buffer_size: int = 0
    frame_count: int = 0
    error_count: int = 0
    overflow_count: int = 0
    silence_duration: float = 0.0

class AudioCapture:
    """
    改进的音频采集器 - 基于小智项目的设计
    增强功能：状态管理、错误恢复、性能监控、静音检测
    """
    
    def __init__(self, 
                 sample_rate: int = AudioConfig.INPUT_SAMPLE_RATE,
                 channels: int = AudioConfig.CHANNELS,
                 frame_duration_ms: int = AudioConfig.FRAME_DURATION,
                 device_id: Optional[int] = None,
                 buffer_size: int = AudioConfig.INPUT_BUFFER_SIZE,
                 silence_threshold: float = 0.01):
        
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.device_id = device_id
        self.buffer_size = buffer_size
        self.silence_threshold = silence_threshold
        
        # 计算帧大小
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        
        # 状态管理
        self.state = AudioState.IDLE
        self._is_closing = False
        self._error_count = 0
        self._max_errors = 5
        
        # 音频流
        self.input_stream = None
        
        # 音频缓冲区
        self.audio_buffer = deque(maxlen=buffer_size)
        self.raw_audio_buffer = deque(maxlen=buffer_size)
        
        # 回调函数
        self.on_audio_data: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_silence_detected: Optional[Callable] = None
        
        # 统计信息
        self.stats = AudioStatistics()
        self.start_time = None
        
        # 事件循环管理
        self._loop = None
        self._thread_id = None
        
        # 设备信息
        self.device_info = {}
        
        # 性能监控
        self._last_stats_time = time.time()
        self._stats_interval = 5.0  # 5秒统计一次
        
        # 静音检测
        self._silence_start_time = None
        self._silence_duration = 0.0
        
    async def initialize(self):
        """初始化音频采集器"""
        try:
            await self._set_state(AudioState.INITIALIZING)
            
            # 检查可用设备
            devices = sd.query_devices()
            logger.info(f"发现 {len(devices)} 个音频设备")
            
            # 列出所有输入设备
            input_devices = []
            for i, device in enumerate(devices):
                max_inputs = device.get('max_inputs', 0)
                max_input_channels = device.get('max_input_channels', 0)
                has_input = max_inputs > 0 or max_input_channels > 0
                
                if has_input:
                    input_devices.append((i, device))
                    logger.info(f"输入设备 {i}: {device['name']} "
                              f"(采样率: {device.get('default_samplerate', 'unknown')}Hz, "
                              f"输入通道: {max_input_channels})")
            
            if not input_devices:
                raise ValueError("没有找到可用的音频输入设备")
            
            # 选择设备
            if self.device_id is None:
                self.device_id = input_devices[0][0]
                logger.info(f"使用第一个可用输入设备: {self.device_id}")
            
            # 检查设备是否有效
            if self.device_id >= len(devices):
                logger.warning(f"设备ID {self.device_id} 无效，使用第一个可用设备")
                self.device_id = input_devices[0][0]
            
            # 获取设备信息
            self.device_info = sd.query_devices(self.device_id)
            logger.info(f"选中设备: {self.device_info['name']}")
            
            # 检查设备能力
            max_inputs = self.device_info.get('max_inputs', 0)
            max_input_channels = self.device_info.get('max_input_channels', 0)
            
            if max_inputs == 0 and max_input_channels == 0:
                logger.warning(f"设备 {self.device_id} 可能不支持音频输入，但将继续尝试")
            
            # 检查采样率兼容性
            device_sample_rate = self.device_info.get('default_samplerate', 16000)
            if device_sample_rate != self.sample_rate:
                logger.warning(f"设备采样率 {device_sample_rate}Hz 与期望 {self.sample_rate}Hz 不同")
            
            await self._set_state(AudioState.IDLE)
            logger.info(f"音频采集器初始化完成")
            
        except Exception as e:
            await self._set_state(AudioState.ERROR)
            logger.error(f"音频采集器初始化失败: {e}")
            raise
        
    async def start_recording(self):
        """开始录音"""
        if self.state == AudioState.RECORDING:
            logger.warning("录音已经在进行中")
            return
            
        try:
            await self._set_state(AudioState.INITIALIZING)
            
            # 保存当前事件循环
            self._loop = asyncio.get_running_loop()
            self._thread_id = threading.get_ident()
            
            # 重置统计信息
            self.stats = AudioStatistics()
            self.start_time = time.time()
            self._last_stats_time = time.time()
            
            # 创建音频输入流
            self.input_stream = sd.InputStream(
                device=self.device_id,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                blocksize=self.frame_size,
                callback=self._audio_callback,
                finished_callback=self._input_finished_callback,
                latency="low"
            )
            
            # 启动音频流
            self.input_stream.start()
            
            await self._set_state(AudioState.RECORDING)
            logger.info(f"开始录音 - 设备: {self.device_id}, "
                       f"采样率: {self.sample_rate}Hz, 帧大小: {self.frame_size}")
            
        except Exception as e:
            await self._set_state(AudioState.ERROR)
            logger.error(f"启动录音失败: {e}")
            raise
        
    def stop_recording(self):
        """停止录音"""
        if self.state not in [AudioState.RECORDING, AudioState.PAUSED]:
            logger.warning("录音未在进行中")
            return
            
        try:
            self._is_closing = True
            
            if self.input_stream:
                self.input_stream.stop()
                self.input_stream.close()
                self.input_stream = None
                
            # 更新统计信息
            if self.start_time:
                self.stats.duration_seconds = time.time() - self.start_time
                
            self._set_state_sync(AudioState.IDLE)
            logger.info(f"停止录音 - 总时长: {self.stats.duration_seconds:.2f}秒, "
                       f"总样本数: {self.stats.total_samples}")
            
        except Exception as e:
            logger.error(f"停止录音失败: {e}")
            
    def pause_recording(self):
        """暂停录音"""
        if self.state == AudioState.RECORDING:
            self._set_state_sync(AudioState.PAUSED)
            logger.info("录音已暂停")
            
    def resume_recording(self):
        """恢复录音"""
        if self.state == AudioState.PAUSED:
            self._set_state_sync(AudioState.RECORDING)
            logger.info("录音已恢复")
            
    def _audio_callback(self, indata, frames, time_info, status):
        """音频数据回调函数"""
        if status:
            if "overflow" in str(status).lower():
                self.stats.overflow_count += 1
                logger.warning(f"音频缓冲区溢出: {status}")
            else:
                logger.warning(f"输入流状态: {status}")

        if self._is_closing or self.state != AudioState.RECORDING:
            return

        try:
            # 更新统计信息
            self.stats.total_samples += frames
            self.stats.frame_count += 1
            self.stats.last_audio_time = time.time()
            
            # 安全地处理音频数据
            if indata is None or indata.size == 0:
                logger.warning("收到空的音频数据")
                return
                
            # 确保数据格式正确
            if len(indata.shape) > 1:
                audio_data = indata[:, 0].flatten()
            else:
                audio_data = indata.flatten()
                
            # 检查数据类型
            if audio_data.dtype != np.int16:
                audio_data = audio_data.astype(np.int16)
            
            # 静音检测
            self._detect_silence(audio_data)
            
            # 添加到原始音频缓冲区
            self.raw_audio_buffer.append(audio_data.copy())
            
            # 转换为字节数据
            audio_bytes = audio_data.tobytes()
            self.stats.total_bytes += len(audio_bytes)
            
            # 添加到音频缓冲区
            self.audio_buffer.append(audio_bytes)
            
            # 安全地触发回调
            self._safe_call_audio_callback(audio_bytes)
            
            # 定期更新统计信息
            self._update_performance_stats()
                
        except Exception as e:
            self.stats.error_count += 1
            logger.error(f"音频回调处理失败: {e}")
            if self.stats.error_count >= self._max_errors:
                logger.error("错误次数过多，停止录音")
                self._set_state_sync(AudioState.ERROR)
            
    def _safe_call_audio_callback(self, audio_data: bytes):
        """安全地调用音频回调"""
        try:
            if self.on_audio_data and self._loop and self._loop.is_running():
                # 检查是否在正确的事件循环中
                if threading.get_ident() == self._thread_id:
                    # 在同一线程中，直接创建任务
                    self._loop.create_task(self._call_audio_callback(audio_data))
                else:
                    # 在不同线程中，使用 call_soon_threadsafe
                    self._loop.call_soon_threadsafe(
                        lambda: self._loop.create_task(self._call_audio_callback(audio_data))
                    )
        except Exception as e:
            logger.error(f"调用音频回调失败: {e}")
            
    def _input_finished_callback(self):
        """输入流结束回调"""
        logger.info("音频输入流已结束")
        
    async def _call_audio_callback(self, audio_data: bytes):
        """异步调用音频数据回调"""
        try:
            if self.on_audio_data:
                await self.on_audio_data(audio_data)
        except Exception as e:
            logger.error(f"音频回调执行失败: {e}")
            
    def _detect_silence(self, audio_data: np.ndarray):
        """检测静音"""
        try:
            # 计算音频能量
            energy = np.mean(np.abs(audio_data))
            
            if energy < self.silence_threshold:
                # 检测到静音
                if self._silence_start_time is None:
                    self._silence_start_time = time.time()
                    logger.debug("检测到静音开始")
            else:
                # 有声音
                if self._silence_start_time is not None:
                    silence_duration = time.time() - self._silence_start_time
                    self._silence_duration = silence_duration
                    self.stats.silence_duration = silence_duration
                    
                    if silence_duration > 2.0:  # 静音超过2秒
                        logger.info(f"检测到长时间静音: {silence_duration:.2f}秒")
                        if self.on_silence_detected:
                            asyncio.create_task(self._call_silence_callback(silence_duration))
                    
                    self._silence_start_time = None
                    
        except Exception as e:
            logger.error(f"静音检测失败: {e}")
            
    async def _call_silence_callback(self, silence_duration: float):
        """调用静音检测回调"""
        try:
            if self.on_silence_detected:
                await self.on_silence_detected(silence_duration)
        except Exception as e:
            logger.error(f"静音回调执行失败: {e}")
            
    def _update_performance_stats(self):
        """更新性能统计"""
        current_time = time.time()
        if current_time - self._last_stats_time >= self._stats_interval:
            self._last_stats_time = current_time
            
            # 计算性能指标
            if self.stats.duration_seconds > 0:
                samples_per_second = self.stats.total_samples / self.stats.duration_seconds
                bytes_per_second = self.stats.total_bytes / self.stats.duration_seconds
                
                logger.debug(f"性能统计 - 采样率: {samples_per_second:.0f}/s, "
                           f"数据率: {bytes_per_second/1024:.1f}KB/s, "
                           f"错误数: {self.stats.error_count}")
                           
    async def _set_state(self, state: AudioState):
        """异步设置状态"""
        old_state = self.state
        self.state = state
        
        if old_state != state:
            logger.info(f"音频状态变化: {old_state.value} -> {state.value}")
            
            if self.on_state_change:
                try:
                    await self.on_state_change(old_state, state)
                except Exception as e:
                    logger.error(f"状态变化回调执行失败: {e}")
                    
    def _set_state_sync(self, state: AudioState):
        """同步设置状态"""
        old_state = self.state
        self.state = state
        
        if old_state != state:
            logger.info(f"音频状态变化: {old_state.value} -> {state.value}")
            
            if self.on_state_change and self._loop and self._loop.is_running():
                try:
                    self._loop.create_task(self.on_state_change(old_state, state))
                except Exception as e:
                    logger.error(f"状态变化回调执行失败: {e}")
            
    def get_audio_buffer(self) -> bytes:
        """获取缓冲区中的所有音频数据"""
        return b''.join(self.audio_buffer)
        
    def get_raw_audio_buffer(self) -> np.ndarray:
        """获取原始音频缓冲区数据"""
        if not self.raw_audio_buffer:
            return np.array([], dtype=np.int16)
        
        # 合并所有音频数据
        return np.concatenate(list(self.raw_audio_buffer))
        
    def clear_buffer(self):
        """清空缓冲区"""
        self.audio_buffer.clear()
        self.raw_audio_buffer.clear()
        self.total_samples = 0
        logger.info("音频缓冲区已清空")
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取录音统计信息"""
        current_time = time.time()
        last_audio_duration = current_time - self.stats.last_audio_time if self.stats.last_audio_time else 0
        
        # 更新持续时间
        if self.start_time:
            self.stats.duration_seconds = current_time - self.start_time
            
        return {
            "state": self.state.value,
            "total_samples": self.stats.total_samples,
            "total_bytes": self.stats.total_bytes,
            "duration_seconds": self.stats.duration_seconds,
            "last_audio_seconds_ago": last_audio_duration,
            "buffer_size": len(self.audio_buffer),
            "raw_buffer_size": len(self.raw_audio_buffer),
            "frame_count": self.stats.frame_count,
            "error_count": self.stats.error_count,
            "overflow_count": self.stats.overflow_count,
            "silence_duration": self.stats.silence_duration,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frame_size": self.frame_size,
            "frame_duration_ms": self.frame_duration_ms,
            "device_id": self.device_id,
            "device_info": self.device_info
        }
        
    def is_audio_active(self, timeout_seconds: float = 1.0) -> bool:
        """检查音频是否活跃"""
        if not self.stats.last_audio_time:
            return False
        return (time.time() - self.stats.last_audio_time) < timeout_seconds
        
    def is_silent(self, threshold_seconds: float = 2.0) -> bool:
        """检查是否处于静音状态"""
        return self.stats.silence_duration > threshold_seconds
        
    def get_audio_level(self) -> float:
        """获取当前音频电平"""
        if not self.raw_audio_buffer:
            return 0.0
        
        try:
            # 获取最新的音频数据
            latest_audio = self.raw_audio_buffer[-1]
            if len(latest_audio) > 0:
                # 计算RMS电平
                rms = np.sqrt(np.mean(latest_audio.astype(np.float32) ** 2))
                return rms / 32768.0  # 归一化到0-1
        except Exception as e:
            logger.error(f"计算音频电平失败: {e}")
            
        return 0.0
        
    def clear_buffer(self):
        """清空缓冲区"""
        self.audio_buffer.clear()
        self.raw_audio_buffer.clear()
        self.stats = AudioStatistics()
        logger.info("音频缓冲区已清空")
        
    def close(self):
        """关闭音频采集器"""
        try:
            self.stop_recording()
            self._is_closing = True
            self._set_state_sync(AudioState.CLOSED)
            logger.info("音频采集器已关闭")
        except Exception as e:
            logger.error(f"关闭音频采集器失败: {e}")
            
    def __del__(self):
        """析构函数"""
        self.close()