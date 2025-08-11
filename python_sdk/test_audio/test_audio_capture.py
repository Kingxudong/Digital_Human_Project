import asyncio
import time
import logging
import sounddevice as sd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def list_audio_devices():
    """列出所有音频设备"""
    try:
        devices = sd.query_devices()
        logger.info(f"发现 {len(devices)} 个音频设备")
        
        for i, device in enumerate(devices):
            logger.info(f"设备 {i}: {device['name']}")
            logger.info(f"  详细信息: {device}")
            
        return devices
    except Exception as e:
        logger.error(f"获取设备列表失败: {e}")
        return []

def test_device_info():
    """测试设备信息获取"""
    try:
        # 获取默认设备
        default_device = sd.default.device
        logger.info(f"默认设备: {default_device}")
        
        # 获取默认输入设备信息
        default_input = sd.query_devices(default_device[0])
        logger.info(f"默认输入设备信息: {default_input}")
        
        # 获取默认输出设备信息
        default_output = sd.query_devices(default_device[1])
        logger.info(f"默认输出设备信息: {default_output}")
        
    except Exception as e:
        logger.error(f"测试设备信息失败: {e}")

def audio_callback(indata, frames, time_info, status):
    """简单的音频回调"""
    if status:
        logger.warning(f"音频状态: {status}")
    
    if indata is not None and indata.size > 0:
        logger.info(f"收到音频数据: {indata.shape}, 帧数: {frames}")

async def test_simple_recording():
    """测试简单录音"""
    try:
        logger.info("开始简单录音测试")
        
        # 创建音频流
        stream = sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=320,
            callback=audio_callback
        )
        
        # 启动流
        stream.start()
        logger.info("音频流已启动")
        
        # 运行5秒
        await asyncio.sleep(5)
        
        # 停止流
        stream.stop()
        stream.close()
        logger.info("音频流已停止")
        
    except Exception as e:
        logger.error(f"简单录音测试失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")

async def main():
    """主函数"""
    logger.info("开始音频设备测试")
    
    # 1. 列出所有设备
    devices = list_audio_devices()
    
    # 2. 测试设备信息
    test_device_info()
    
    # 3. 测试简单录音
    await test_simple_recording()
    
    logger.info("测试完成")

if __name__ == "__main__":
    asyncio.run(main())