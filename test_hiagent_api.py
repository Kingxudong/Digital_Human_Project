#!/usr/bin/env python3
"""
测试 HiAgent API 连接
"""

import requests
import json

def test_hiagent_api():
    """测试 HiAgent API 连接"""
    
    # 配置
    base_url = "https://hiagent.volcenginepaas.com/api/proxy/api/v1"
    api_key = "d262djub2no6qhvbn6o0"
    
    headers = {
        'Apikey': api_key,
        'Content-Type': 'application/json'
    }
    
    # 测试创建会话
    url = f"{base_url}/create_conversation"
    data = {
        "UserID": "test_user",
        "Inputs": {}
    }
    
    print(f"测试 URL: {url}")
    print(f"请求数据: {json.dumps(data, indent=2)}")
    print(f"请求头: {headers}")
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            print("✅ API 连接成功！")
            return True
        else:
            print(f"❌ API 连接失败，状态码: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False

if __name__ == "__main__":
    print("开始测试 HiAgent API 连接...")
    test_hiagent_api() 