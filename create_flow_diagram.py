#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统详细流程图生成器
生成后端服务器的详细流程图并保存为PNG格式
"""

import os
import subprocess
from pathlib import Path

def create_mermaid_diagram():
    """创建Mermaid流程图代码"""
    
    mermaid_code = """
graph TD
    %% 系统启动
    A[系统启动] --> B[startup_event]
    B --> B1[启动WebSocket服务器]
    B --> B2[初始化LLM客户端]
    B --> B3[初始化TTS客户端]
    B --> B4[初始化数字人客户端]
    B --> B5[初始化STT客户端]
    B --> B6[启动清理任务]
    
    %% 数字人加入房间流程
    C[前端请求加入房间] --> D[join_room]
    D --> D1{检查现有会话}
    D1 -->|存在且活跃| D2[返回已在房间中]
    D1 -->|不存在或过期| D3[清理过期会话]
    D3 --> D4{检查冷却期}
    D4 -->|在冷却期| D5[返回429错误]
    D4 -->|不在冷却期| D6[获取连接锁]
    D6 --> D7[join_room_task]
    D7 --> D8[digital_human_client.connect]
    D8 --> D9[健康检查]
    D9 --> D10[digital_human_client.start_live_rtc]
    D10 --> D11[记录活跃会话]
    D11 --> D12[返回成功响应]
    
    %% 流式查询处理流程
    E[前端发送查询] --> F[process_query_stream]
    F --> F1{验证客户端状态}
    F1 -->|未初始化| F2[返回500错误]
    F1 -->|已初始化| F3[取消之前的流]
    F3 --> F4[register_stream_session]
    F4 --> F5[生成会话ID]
    F5 --> F6[llm_client.create_conversation]
    F6 --> F7[stream_pipeline]
    
    %% 流式处理管道
    F7 --> G[发送开始信号]
    G --> H[llm_client.chat_stream]
    H --> I[处理LLM响应]
    I --> I1[提取文本内容]
    I1 --> I2[累积文本缓冲]
    I2 --> I3[检查完整句子]
    I3 -->|未完成| I4[继续累积]
    I3 -->|完成| I5[句子处理]
    
    %% TTS处理流程
    I5 --> J[ensure_tts_connection]
    J --> J1{检查TTS连接}
    J1 -->|断开| J2[重新连接TTS]
    J1 -->|正常| J3[safe_tts_synthesize]
    J3 --> J4[tts_client.synthesize_text]
    J4 --> J5[生成音频块]
    J5 --> J6[数字人驱动]
    
    %% 数字人驱动流程
    J6 --> K[digital_human_client.drive_with_streaming_audio]
    K --> K1[发送音频数据]
    K1 --> K2[数字人动画]
    K2 --> K3[返回音频进度]
    K3 --> K4[发送完成信号]
    
    %% 语音控制流程
    L[前端语音控制] --> M[single_button_voice_control]
    M --> M1{检查录音状态}
    M1 -->|未录音| M2[开始录音]
    M2 --> M3[MicrophoneRecorder.start_recording]
    M3 --> M4[返回录音开始]
    M1 -->|正在录音| M5[停止录音]
    M5 --> M6[MicrophoneRecorder.stop_recording]
    M6 --> M7[获取音频数据]
    M7 --> M8[AsrWsClient语音识别]
    M8 --> M9[获取识别文本]
    M9 --> M10[调用process_query_stream]
    
    %% WebSocket音频处理流程
    N[前端WebSocket连接] --> O[websocket_handler]
    O --> O1[建立连接]
    O1 --> O2[handle_json_message]
    O2 --> O3[handle_audio_data]
    O3 --> O4[convert_pcm_to_wav]
    O4 --> O5[STT客户端处理]
    O5 --> O6[stt_client.send_audio]
    O6 --> O7[返回识别结果]
    
    %% 离开房间流程
    P[前端离开房间] --> Q[leave_room]
    Q --> Q1[cancel_streams_by_live_id]
    Q1 --> Q2[取消所有流式会话]
    Q2 --> Q3[digital_human_client.stop_live]
    Q3 --> Q4[断开连接]
    Q4 --> Q5[清理会话]
    Q5 --> Q6[返回成功响应]
    
    %% 连接重置流程
    R[重置连接请求] --> S[reset_connections]
    S --> S1[取消所有请求]
    S1 --> S2[断开所有客户端]
    S2 --> S3[清理会话]
    S3 --> S4[返回重置结果]
    
    %% 状态检查流程
    T[状态检查请求] --> U[get_connection_status]
    U --> U1[检查数字人状态]
    U1 --> U2[检查TTS状态]
    U2 --> U3[健康检查]
    U3 --> U4[返回状态信息]
    
    %% 错误处理流程
    V[异常发生] --> W[异常处理器]
    W --> W1[http_exception_handler]
    W --> W2[validation_exception_handler]
    W --> W3[general_exception_handler]
    W1 --> W4[返回友好错误信息]
    W2 --> W4
    W3 --> W4
    
    %% 清理任务
    X[cleanup_pending_requests] --> X1[清理已完成任务]
    X1 --> X2[清理过期失败请求]
    X2 --> X3[等待30秒]
    X3 --> X1
    
    %% 样式定义
    classDef startEnd fill:#e1f5fe
    classDef process fill:#f3e5f5
    classDef decision fill:#fff3e0
    classDef error fill:#ffebee
    classDef client fill:#e8f5e8
    
    class A,X startEnd
    class B,D,F,H,J,K,M,O,Q,S,U,W process
    class D1,D4,F1,I3,J1,M1 decision
    class F2,D5,W error
    class B2,B3,B4,B5,D8,J4,K,O5 client
    """
    
    return mermaid_code.strip()

def save_mermaid_to_file(mermaid_code, filename="system_flow_diagram.mmd"):
    """保存Mermaid代码到文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(mermaid_code)
    print(f"Mermaid代码已保存到: {filename}")

def create_html_viewer(mermaid_code, output_file):
    """创建HTML查看器"""
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>系统详细流程图</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }}
        .mermaid {{
            text-align: center;
        }}
        .download-section {{
            margin-top: 20px;
            text-align: center;
        }}
        .download-btn {{
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            margin: 5px;
        }}
        .download-btn:hover {{
            background-color: #0056b3;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>AI对话系统详细流程图</h1>
        <div class="mermaid">
{mermaid_code}
        </div>
        <div class="download-section">
            <p>流程图说明：</p>
            <ul style="text-align: left; max-width: 800px; margin: 0 auto;">
                <li><strong>蓝色节点</strong>：系统启动和清理任务</li>
                <li><strong>紫色节点</strong>：主要处理函数</li>
                <li><strong>橙色节点</strong>：决策判断点</li>
                <li><strong>红色节点</strong>：错误处理</li>
                <li><strong>绿色节点</strong>：客户端操作</li>
            </ul>
            <br>
            <a href="system_flow_diagram.png" class="download-btn" download>下载PNG图片</a>
            <a href="system_flow_diagram.mmd" class="download-btn" download>下载Mermaid源码</a>
        </div>
    </div>
    
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});
    </script>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML查看器已创建: {output_file}")

def main():
    """主函数"""
    print("=== AI对话系统详细流程图生成器 ===")
    
    # 创建输出目录
    output_dir = Path("flow_diagrams")
    output_dir.mkdir(exist_ok=True)
    
    # 生成Mermaid代码
    mermaid_code = create_mermaid_diagram()
    
    # 保存Mermaid源码
    mmd_file = output_dir / "system_flow_diagram.mmd"
    save_mermaid_to_file(mermaid_code, str(mmd_file))
    
    # 创建HTML查看器
    html_file = output_dir / "system_flow_diagram.html"
    create_html_viewer(mermaid_code, str(html_file))
    
    print("\n=== 生成完成 ===")
    print(f"输出目录: {output_dir.absolute()}")
    print(f"Mermaid源码: {mmd_file}")
    print(f"HTML查看器: {html_file}")
    print(f"PNG图片: {output_dir / 'system_flow_diagram.png'}")
    
    print("\n使用说明:")
    print("1. 打开HTML文件在浏览器中查看交互式流程图")
    print("2. 使用Mermaid源码在在线编辑器中编辑")
    print("3. 查看PNG图片用于文档或演示")

if __name__ == "__main__":
    main()
