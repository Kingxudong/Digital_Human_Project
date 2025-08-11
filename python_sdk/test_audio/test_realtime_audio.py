import asyncio
import time
import logging
import uuid
from realtime_audio_handler import RealTimeAudioHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_stt_result(text: str, is_final: bool, confidence: float):
    """测试STT结果回调"""
    logger.info(f"STT结果: {text} (最终: {is_final}, 置信度: {confidence})")

async def test_error(error: str):
    """测试错误回调"""
    logger.error(f"处理错误: {error}")

async def test_status_change(status: str):
    """测试状态变化回调"""
    logger.info(f"状态变化: {status}")

async def main():
    """主测试函数"""
    logger.info("开始实时音频处理测试")
    
    # 创建会话ID
    session_id = str(uuid.uuid4())
    
    # 创建实时音频处理器
    # 注意：这里需要一个WebSocket服务器地址
    # 您可以先用一个模拟的地址进行测试
    handler = RealTimeAudioHandler(
        server_url="ws://localhost:9000/audio",  # 模拟服务器地址
        session_id=session_id
    )
    
    # 设置回调
    handler.on_stt_result = test_stt_result
    handler.on_error = test_error
    handler.on_status_change = test_status_change
    
    try:
        # 开始处理
        await handler.start()
        
        logger.info("实时音频处理已开始，请说话...")
        logger.info("按 Ctrl+C 停止处理")
        
        # 运行一段时间
        start_time = time.time()
        while time.time() - start_time < 15:  # 运行15秒
            # 每秒打印一次统计信息
            if int(time.time() - start_time) % 5 == 0:  # 每5秒打印一次
                stats = handler.get_statistics()
                logger.info(f"处理统计: {stats}")
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
    finally:
        # 停止处理
        await handler.stop()
        
        # 打印最终统计
        final_stats = handler.get_statistics()
        logger.info(f"最终统计: {final_stats}")
        
        logger.info("测试完成")

if __name__ == "__main__":
    asyncio.run(main())