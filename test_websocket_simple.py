#!/usr/bin/env python
import asyncio
import websockets
import json

async def test_websocket_simple():
    """简单测试WebSocket连接"""
    try:
        uri = "ws://localhost:9002/audio"
        print(f"正在连接到: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket连接成功!")
            
            # 发送简单的hello消息
            hello_message = {
                "type": "hello",
                "session_id": "test_simple",
                "capabilities": {
                    "audio": True,
                    "stt": True,
                    "pcm_format": True
                }
            }
            
            print(f"发送hello消息: {hello_message}")
            await websocket.send(json.dumps(hello_message))
            
            # 等待响应
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"✅ 收到响应: {response}")
            except asyncio.TimeoutError:
                print("❌ 5秒内没有收到响应")
                return False
            
            return True
            
    except Exception as e:
        print(f"❌ WebSocket测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_websocket_simple())
    if result:
        print("🎉 WebSocket连接测试成功!")
    else:
        print("💥 WebSocket连接测试失败!")
