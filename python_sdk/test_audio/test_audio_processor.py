import asyncio
import time
import logging
import numpy as np
from audio_processor import AudioProcessor
from audio_capture import AudioCapture

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_audio_callback(audio_data: bytes):
    """测试音频数据回调"""
    logger.info(f"收到音频数据: {len(audio_data)} 字节")

async def test_processor_callback(encoded_data: bytes):
    """测试处理器回调"""
    logger.info(f"收到编码数据: {len(encoded_data)} 字节")

async def main():
    """主测试函数"""
    logger.info("开始音频处理器测试")
    
    # 创建音频采集器和处理器
    capture = AudioCapture()
    processor = AudioProcessor()
    
    try:
        # 初始化
        await capture.initialize()
        
        # 设置回调
        capture.on_audio_data = test_audio_callback
        
        # 开始录音
        await capture.start_recording()
        
        logger.info("录音已开始，请说话...")
        logger.info("按 Ctrl+C 停止录音")
        
        # 运行一段时间
        start_time = time.time()
        while time.time() - start_time < 10:  # 运行10秒
            # 每秒处理一次音频数据
            if int(time.time() - start_time) % 1 == 0:
                # 获取音频数据
                audio_data = capture.get_audio_buffer()
                if len(audio_data) > 0:
                    # 处理音频数据
                    encoded_data = processor.process_audio_file(audio_data)
                    if len(encoded_data) > 0:
                        logger.info(f"处理音频: {len(audio_data)} -> {len(encoded_data)} 字节")
                        test_processor_callback(encoded_data)
                    
                    # 清空缓冲区
                    capture.clear_buffer()
                
                # 打印统计信息
                capture_stats = capture.get_statistics()
                processor_stats = processor.get_statistics()
                logger.info(f"采集统计: {capture_stats}")
                logger.info(f"处理统计: {processor_stats}")
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
    finally:
        # 停止录音
        capture.stop_recording()
        
        # 打印最终统计
        final_capture_stats = capture.get_statistics()
        final_processor_stats = processor.get_statistics()
        logger.info(f"最终采集统计: {final_capture_stats}")
        logger.info(f"最终处理统计: {final_processor_stats}")
        
        logger.info("测试完成")

if __name__ == "__main__":
    asyncio.run(main())