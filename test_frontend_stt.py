#!/usr/bin/env python3
"""
测试前端录音+后端STT处理功能
"""

import asyncio
import websockets
import json
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_frontend_stt():
    """测试前端录音+后端STT处理"""
    
    # 连接WebSocket
    uri = "ws://localhost:9002/audio"
    logger.info(f"连接到WebSocket: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("WebSocket连接成功")
            
            # 发送hello消息
            hello_msg = {
                "type": "hello",
                "data": {
                    "message": "测试连接"
                }
            }
            await websocket.send(json.dumps(hello_msg, ensure_ascii=False))
            logger.info("发送hello消息")
            
            # 等待响应
            response = await websocket.recv()
            response_data = json.loads(response)
            logger.info(f"收到响应: {response_data}")
            
            # 发送录音开始消息
            start_msg = {
                "type": "recording_start",
                "data": {
                    "message": "开始录音"
                }
            }
            await websocket.send(json.dumps(start_msg, ensure_ascii=False))
            logger.info("发送录音开始消息")
            
            # 等待响应
            response = await websocket.recv()
            response_data = json.loads(response)
            logger.info(f"收到响应: {response_data}")
            
            # 发送模拟音频数据（1秒的静音）
            sample_rate = 16000
            channels = 1
            bits_per_sample = 16
            duration_ms = 1000  # 1秒
            
            # 计算音频数据大小
            bytes_per_sample = bits_per_sample // 8
            samples_per_ms = sample_rate // 1000
            total_samples = samples_per_ms * duration_ms
            audio_data_size = total_samples * channels * bytes_per_sample
            
            # 生成静音数据（全零）
            audio_data = b'\x00' * audio_data_size
            
            logger.info(f"发送音频数据: {len(audio_data)} 字节")
            
            # 发送音频数据
            await websocket.send(audio_data)
            
            # 等待STT响应
            start_time = time.time()
            timeout = 10  # 10秒超时
            
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    response_data = json.loads(response)
                    logger.info(f"收到STT响应: {response_data}")
                    
                    # 检查是否是STT结果
                    if response_data.get("type") == "stt_result":
                        text = response_data.get("data", {}).get("text", "")
                        is_final = response_data.get("data", {}).get("is_final", False)
                        logger.info(f"STT结果: '{text}' (最终: {is_final})")
                        
                        if is_final and text.strip():
                            logger.info("✅ STT处理成功！")
                            break
                    elif response_data.get("type") == "audio_received":
                        logger.info("音频数据已接收")
                    elif response_data.get("type") == "stt_error":
                        logger.error(f"STT错误: {response_data}")
                        break
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"接收响应时出错: {e}")
                    break
            
            # 发送录音结束消息
            end_msg = {
                "type": "recording_end",
                "data": {
                    "message": "结束录音"
                }
            }
            await websocket.send(json.dumps(end_msg, ensure_ascii=False))
            logger.info("发送录音结束消息")
            
            # 等待响应
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                logger.info(f"收到响应: {response_data}")
            except asyncio.TimeoutError:
                logger.info("没有收到录音结束响应")
            
            logger.info("测试完成")
            
    except Exception as e:
        logger.error(f"测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_frontend_stt())
