#!/usr/bin/env python
import asyncio
import websockets
import json

async def test_websocket():
    """测试WebSocket连接"""
    try:
        # 连接到WebSocket服务器
        uri = "ws://localhost:9002/audio"
        print(f"正在连接到: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("WebSocket连接成功!")
            
            # 发送hello消息
            hello_message = {
                "type": "hello",
                "session_id": "test_session_123",
                "capabilities": {
                    "audio": True,
                    "stt": True,
                    "pcm_format": True
                },
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": 16000,
                    "channels": 1,
                    "bits_per_sample": 16
                }
            }
            
            print(f"发送hello消息: {hello_message}")
            await websocket.send(json.dumps(hello_message))
            
            # 等待响应
            response = await websocket.recv()
            print(f"收到响应: {response}")
            
            # 发送录音开始消息
            start_message = {
                "type": "recording_start",
                "session_id": "test_session_123"
            }
            
            print(f"发送录音开始消息: {start_message}")
            await websocket.send(json.dumps(start_message))
            
            # 等待响应
            response = await websocket.recv()
            print(f"收到响应: {response}")
            
            # 发送一些测试音频数据（模拟PCM数据）
            test_audio = b'\x00\x00' * 1024  # 1KB的静音数据
            
            print(f"发送测试音频数据: {len(test_audio)} 字节")
            await websocket.send(test_audio)
            
            # 等待一段时间看是否有STT结果
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"收到STT响应: {response}")
            except asyncio.TimeoutError:
                print("5秒内没有收到STT响应")
            
            # 发送录音结束消息
            end_message = {
                "type": "recording_end",
                "session_id": "test_session_123"
            }
            
            print(f"发送录音结束消息: {end_message}")
            await websocket.send(json.dumps(end_message))
            
            # 等待响应
            response = await websocket.recv()
            print(f"收到响应: {response}")
            
    except Exception as e:
        print(f"WebSocket测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())
