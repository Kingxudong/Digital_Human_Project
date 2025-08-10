#!/usr/bin/env python3
"""
测试并发限制错误处理
"""

import requests
import json
import time

def test_join_room():
    """测试加入房间"""
    url = "http://localhost:8000/api/digital_human_develop/join_room"
    
    # 测试数据
    data = {
        "live_id": f"test_live_{int(time.time())}",
        "avatar_type": "3min",
        "role": "250623-zhibo-linyunzhi"
    }
    
    try:
        print(f"测试加入房间: {data['live_id']}")
        response = requests.post(url, json=data, timeout=10)
        
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 429:
            print("✅ 正确返回 429 状态码（并发限制）")
            return True
        elif response.status_code == 500:
            print("❌ 返回 500 状态码，错误处理可能有问题")
            return False
        elif response.status_code == 200:
            print("✅ 成功加入房间")
            return True
        else:
            print(f"❌ 意外的状态码: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_health():
    """测试健康检查"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 服务健康状态: {data}")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False

def main():
    """主函数"""
    print("并发限制错误处理测试")
    print("="*40)
    
    # 检查服务状态
    if not test_health():
        print("服务不可用，请先启动后端服务")
        return
    
    print("\n开始测试并发限制...")
    
    # 多次测试，触发并发限制
    for i in range(3):
        print(f"\n--- 测试 {i+1} ---")
        success = test_join_room()
        if not success:
            break
        time.sleep(1)
    
    print("\n测试完成")

if __name__ == "__main__":
    main() 