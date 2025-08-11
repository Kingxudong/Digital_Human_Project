#!/usr/bin/env python
import asyncio
import websockets
import json
import time

async def simulate_frontend_connection():
    """模拟前端WebSocket连接"""
    try:
        uri = "ws://localhost:9002/audio"
        print(f"🔄 正在连接到: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket连接成功!")
            
            # 生成session ID（模拟前端）
            session_id = f"session_{int(time.time() * 1000)}_{int(time.time() * 1000) % 10000}"
            print(f"📝 会话ID: {session_id}")
            
            # 发送hello消息（模拟前端）
            hello_message = {
                "type": "hello",
                "session_id": session_id,
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
            
            print(f"📤 发送hello消息: {hello_message}")
            await websocket.send(json.dumps(hello_message))
            
            # 等待hello_ack响应
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"📥 收到hello响应: {response}")
                
                # 解析响应
                response_data = json.loads(response)
                if response_data.get("type") == "hello_ack":
                    print("✅ Hello握手成功!")
                else:
                    print(f"❌ 意外的响应类型: {response_data.get('type')}")
                    return False
                    
            except asyncio.TimeoutError:
                print("❌ 5秒内没有收到hello响应")
                return False
            
            # 发送录音开始消息
            start_message = {
                "type": "recording_start",
                "session_id": session_id
            }
            
            print(f"📤 发送录音开始消息: {start_message}")
            await websocket.send(json.dumps(start_message))
            
            # 等待录音开始确认
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"📥 收到录音开始响应: {response}")
                
                response_data = json.loads(response)
                if response_data.get("type") == "recording_start_ack":
                    print("✅ 录音开始确认成功!")
                else:
                    print(f"❌ 意外的响应类型: {response_data.get('type')}")
                    return False
                    
            except asyncio.TimeoutError:
                print("❌ 5秒内没有收到录音开始响应")
                return False
            
            # 发送一些模拟音频数据
            print("🎵 发送模拟音频数据...")
            for i in range(3):
                # 模拟1KB的音频数据
                audio_data = b'\x00\x00' * 512  # 1KB的静音数据
                await websocket.send(audio_data)
                print(f"📤 发送音频块 {i+1}/3: {len(audio_data)} 字节")
                await asyncio.sleep(0.5)  # 等待500ms
            
            # 发送录音结束消息
            end_message = {
                "type": "recording_end",
                "session_id": session_id
            }
            
            print(f"📤 发送录音结束消息: {end_message}")
            await websocket.send(json.dumps(end_message))
            
            # 等待录音结束确认
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"📥 收到录音结束响应: {response}")
                
                response_data = json.loads(response)
                if response_data.get("type") == "recording_end_ack":
                    print("✅ 录音结束确认成功!")
                elif response_data.get("type") == "audio_received":
                    print("✅ 音频数据接收确认成功!")
                else:
                    print(f"❌ 意外的响应类型: {response_data.get('type')}")
                    return False
                    
            except asyncio.TimeoutError:
                print("❌ 5秒内没有收到录音结束响应")
                return False
            
            print("🎉 前端模拟测试完成!")
            return True
            
    except Exception as e:
        print(f"❌ 前端模拟测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 开始前端WebSocket连接模拟测试...")
    result = asyncio.run(simulate_frontend_connection())
    if result:
        print("🎉 前端模拟测试成功!")
    else:
        print("💥 前端模拟测试失败!")
