#!/usr/bin/env python3
"""
测试 join_room 接口的脚本
用于排查接口无响应的问题
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# 配置
API_BASE_URL = "http://localhost:8000"
TEST_LIVE_ID = f"test_live_{int(time.time())}"

async def test_health_check():
    """测试健康检查接口"""
    print(f"[{datetime.now()}] 测试健康检查接口...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 健康检查成功: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return True
                else:
                    print(f"❌ 健康检查失败: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False

async def test_connection_status():
    """测试连接状态接口"""
    print(f"[{datetime.now()}] 测试连接状态接口...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/api/connection_status") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 连接状态: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return True
                else:
                    print(f"❌ 连接状态失败: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ 连接状态异常: {e}")
        return False

async def test_join_room():
    """测试 join_room 接口"""
    print(f"[{datetime.now()}] 测试 join_room 接口...")
    
    # 请求参数
    payload = {
        "live_id": TEST_LIVE_ID,
        "avatar_type": "3min",
        "role": "250623-zhibo-linyunzhi",
        "rtc_room_id": "hi_agent_tta_demo",
        "rtc_uid": "digital_human_develop"
    }
    
    print(f"请求参数: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 设置超时时间
            timeout = aiohttp.ClientTimeout(total=120)  # 2分钟超时
            
            start_time = time.time()
            async with session.post(
                f"{API_BASE_URL}/api/digital_human_develop/join_room",
                json=payload,
                timeout=timeout
            ) as response:
                end_time = time.time()
                duration = end_time - start_time
                
                print(f"响应状态: {response.status}")
                print(f"响应时间: {duration:.2f}秒")
                
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ join_room 成功: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return True
                else:
                    try:
                        error_data = await response.json()
                        print(f"❌ join_room 失败: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
                    except:
                        error_text = await response.text()
                        print(f"❌ join_room 失败: {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        print(f"❌ join_room 超时 (超过120秒)")
        return False
    except Exception as e:
        print(f"❌ join_room 异常: {e}")
        return False

async def test_leave_room():
    """测试 leave_room 接口"""
    print(f"[{datetime.now()}] 测试 leave_room 接口...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(f"{API_BASE_URL}/api/digital_human_develop/leave_room/{TEST_LIVE_ID}") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ leave_room 成功: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return True
                else:
                    print(f"❌ leave_room 失败: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ leave_room 异常: {e}")
        return False

async def main():
    """主测试流程"""
    print("=" * 60)
    print("开始测试 join_room 接口")
    print("=" * 60)
    
    # 1. 健康检查
    if not await test_health_check():
        print("❌ 健康检查失败，停止测试")
        return
    
    # 2. 连接状态检查
    await test_connection_status()
    
    # 3. 测试 join_room
    join_success = await test_join_room()
    
    # 4. 如果成功，测试 leave_room
    if join_success:
        await asyncio.sleep(2)  # 等待2秒
        await test_leave_room()
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main()) 