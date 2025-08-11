# 在 develop/python_sdk/ 目录下创建 audio_config.py 文件

import platform
from typing import Optional

class AudioConfig:
    """
    音频配置类 - 基于小智项目的设计
    """
    
    # 固定配置
    INPUT_SAMPLE_RATE = 16000  # 输入采样率16kHz
    OUTPUT_SAMPLE_RATE = 16000  # 输出采样率16kHz (数字人项目使用)
    CHANNELS = 1  # 单声道
    
    # 帧长度配置 (毫秒)
    FRAME_DURATION = 20  # 20ms帧长度，适合实时处理
    
    # 根据采样率计算帧大小
    INPUT_FRAME_SIZE = int(INPUT_SAMPLE_RATE * (FRAME_DURATION / 1000))  # 320 samples
    OUTPUT_FRAME_SIZE = int(OUTPUT_SAMPLE_RATE * (FRAME_DURATION / 1000))  # 320 samples
    
    # 缓冲区配置
    INPUT_BUFFER_SIZE = 1000  # 输入缓冲区大小
    OUTPUT_BUFFER_SIZE = 500   # 输出缓冲区大小
    
    # 音频格式
    AUDIO_FORMAT = "opus"  # 使用Opus编码
    PCM_DTYPE = "int16"    # PCM数据类型
    
    @classmethod
    def get_frame_duration(cls) -> int:
        """获取帧长度，可根据设备性能调整"""
        try:
            # 检测ARM架构设备（如树莓派）
            machine = platform.machine().lower()
            arm_archs = ["arm", "aarch64", "armv7l", "armv6l"]
            is_arm_device = any(arch in machine for arch in arm_archs)
            
            if is_arm_device:
                # ARM设备使用较大帧长以减少CPU负载
                return 60
            else:
                # 其他设备使用低延迟
                return 20
                
        except Exception:
            # 默认使用20ms
            return 20
    
    @classmethod
    def get_device_info(cls) -> dict:
        """获取设备音频信息"""
        try:
            import sounddevice as sd
            
            # 获取默认设备信息
            input_device = sd.query_devices(sd.default.device[0])
            output_device = sd.query_devices(sd.default.device[1])
            
            return {
                "input_device": {
                    "name": input_device.get("name", "Unknown"),
                    "sample_rate": input_device.get("default_samplerate", 16000),
                    "channels": input_device.get("max_input_channels", 1)
                },
                "output_device": {
                    "name": output_device.get("name", "Unknown"),
                    "sample_rate": output_device.get("default_samplerate", 16000),
                    "channels": output_device.get("max_output_channels", 1)
                }
            }
        except Exception as e:
            return {
                "error": str(e),
                "input_device": {"sample_rate": 16000, "channels": 1},
                "output_device": {"sample_rate": 16000, "channels": 1}
            }