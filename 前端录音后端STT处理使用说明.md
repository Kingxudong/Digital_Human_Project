# 前端录音 + 后端STT处理使用说明

## 概述

本项目已实现两种录音模式：
1. **后端录音模式**：后端服务器直接录音，后端STT处理
2. **前端录音模式**：前端浏览器录音，通过WebSocket实时发送音频数据到后端进行STT处理

## 架构对比

### 后端录音模式（原有）
- **录音设备**：后端服务器麦克风
- **音频处理**：后端PyAudio
- **STT服务**：后端连接SAUC服务
- **优点**：前端简单，后端集中处理
- **缺点**：需要后端有麦克风设备

### 前端录音模式（新增）
- **录音设备**：用户浏览器麦克风
- **音频处理**：前端AudioContext + ScriptProcessorNode
- **数据传输**：WebSocket实时传输
- **STT服务**：后端连接SAUC服务
- **优点**：用户设备录音，无需后端麦克风
- **缺点**：需要用户授权麦克风权限

## 技术实现

### 后端实现

#### 1. WebSocket服务器
```python
# 启动WebSocket服务器
async def start_websocket_server():
    server = await websockets.serve(
        websocket_handler,
        "localhost",
        9002,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=10
    )
```

#### 2. 音频数据处理
```python
async def handle_audio_data(session_id: str, audio_data: bytes):
    # 获取或创建ASR客户端
    if session_id not in stt_clients:
        asr_client = AsrWsClient(
            url="wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel"
        )
        stt_clients[session_id] = asr_client
        
        # 初始化ASR连接
        await asr_client.create_connection()
        await asr_client.send_full_client_request()
    
    # 发送音频数据到ASR服务进行识别
    async for response in asr_client.start_audio_stream(
        segment_size=asr_client.get_segment_size(audio_data),
        content=audio_data,
    ):
        if response.is_final_result():
            final_text = response.get_text()
            # 发送最终识别结果给前端
            await send_json_message(session_id, {
                "type": "stt_result",
                "data": {
                    "text": final_text,
                    "is_final": True,
                    "confidence": 0.95
                }
            })
```

#### 3. 消息处理
```python
async def handle_json_message(session_id: str, data: dict):
    message_type = data.get("type", "unknown")
    
    if message_type == "hello":
        # 前端连接消息
        await send_json_message(session_id, {
            "type": "hello_ack",
            "session_id": session_id,
            "status": "ready"
        })
        
    elif message_type == "recording_start":
        # 录音开始
        await send_json_message(session_id, {
            "type": "recording_start_ack",
            "session_id": session_id
        })
        
    elif message_type == "recording_end":
        # 录音结束
        await send_json_message(session_id, {
            "type": "recording_end_ack",
            "session_id": session_id
        })
```

### 前端实现

#### 1. AudioRecorder组件
```typescript
const AudioRecorder: React.FC<AudioRecorderProps> = ({
  onSTTResult,
  onError,
  onStatusChange,
  websocketUrl,
  sessionId
}) => {
  // WebSocket连接
  const connectWebSocket = useCallback(async () => {
    const ws = new WebSocket(websocketUrl);
    ws.onopen = () => {
      // 发送hello消息
      ws.send(JSON.stringify({
        type: 'hello',
        session_id: sessionId,
        capabilities: {
          audio: true,
          stt: true,
          pcm_format: true
        },
        audio_params: {
          format: 'pcm',
          sample_rate: 16000,
          channels: 1,
          bits_per_sample: 16
        }
      }));
    };
  }, []);

  // 音频处理
  const initializeAudio = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });
    
    const audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    
    processor.onaudioprocess = (event) => {
      if (isRecording && websocketRef.current?.readyState === WebSocket.OPEN) {
        const inputBuffer = event.inputBuffer;
        const pcmData = inputBuffer.getChannelData(0);
        
        // 转换为16位PCM
        const pcm16 = new Int16Array(pcmData.length);
        for (let i = 0; i < pcmData.length; i++) {
          pcm16[i] = Math.max(-32768, Math.min(32767, pcmData[i] * 32768));
        }
        
        // 发送音频数据
        websocketRef.current.send(pcm16.buffer);
      }
    };
  }, []);
};
```

#### 2. Meeting页面集成
```typescript
const Meeting: React.FC = () => {
  const [useFrontendRecording, setUseFrontendRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState('未连接');
  
  // 前端录音处理函数
  const handleFrontendSTTResult = (text: string, isFinal: boolean, confidence: number) => {
    if (isFinal) {
      setInputMessage(text);
      // 自动发送识别到的文本
      if (text.trim()) {
        sendMessageInternal(text);
      }
    } else {
      // 中间结果
      setInputMessage(text);
    }
  };

  return (
    <div>
      {/* 录音模式切换 */}
      <Switch
        checked={useFrontendRecording}
        onChange={setUseFrontendRecording}
        checkedChildren="前端录音"
        unCheckedChildren="后端录音"
      />
      
      {/* 录音按钮 */}
      {useFrontendRecording ? (
        <AudioRecorder
          onSTTResult={handleFrontendSTTResult}
          onError={handleRecordingError}
          onStatusChange={handleRecordingStatusChange}
          websocketUrl="ws://localhost:9002/audio"
          sessionId={`session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`}
        />
      ) : (
        <Button onClick={isRecording ? stopRecording : startRecording}>
          {isRecording ? '停止录音' : '开始录音'}
        </Button>
      )}
    </div>
  );
};
```

## 使用方法

### 1. 启动后端服务
```bash
cd develop/python_sdk
python backend_server.py
```

后端服务将启动：
- HTTP API服务器：`http://localhost:9000`
- WebSocket服务器：`ws://localhost:9002/audio`

### 2. 启动前端服务
```bash
cd develop
npm start
```

前端服务将启动：`http://localhost:3000`

### 3. 使用录音功能

1. **进入会议页面**
   - 访问 `http://localhost:3000`
   - 输入房间ID和用户ID
   - 点击"Join Room"

2. **选择录音模式**
   - 在聊天输入区域找到"录音模式"开关
   - 切换到"前端录音"模式

3. **开始录音**
   - 点击录音按钮开始录音
   - 说话完成后再次点击停止录音
   - 系统会自动识别语音并填入输入框

4. **发送消息**
   - 识别结果会自动填入输入框
   - 可以手动编辑或直接发送
   - 点击"Send"按钮发送消息

## 技术特点

### 音频格式
- **采样率**：16kHz
- **声道数**：单声道
- **位深度**：16位
- **格式**：PCM

### 实时处理
- **音频传输**：WebSocket实时传输
- **STT处理**：后端实时识别
- **结果返回**：实时返回识别结果

### 错误处理
- **连接断开**：自动重连机制
- **权限错误**：用户友好的错误提示
- **识别失败**：详细的错误信息

## 注意事项

1. **浏览器兼容性**
   - 需要支持WebRTC的现代浏览器
   - 需要用户授权麦克风权限

2. **网络要求**
   - 需要稳定的网络连接
   - WebSocket连接需要保持活跃

3. **音频质量**
   - 建议在安静环境中使用
   - 避免背景噪音干扰

4. **性能考虑**
   - 音频数据实时传输可能消耗较多带宽
   - 建议在局域网或高速网络环境下使用

## 故障排除

### 常见问题

1. **麦克风权限被拒绝**
   - 检查浏览器设置
   - 重新授权麦克风权限

2. **WebSocket连接失败**
   - 检查后端服务是否启动
   - 检查防火墙设置

3. **音频识别失败**
   - 检查网络连接
   - 确认音频输入正常
   - 查看后端日志

4. **录音按钮无响应**
   - 检查浏览器控制台错误
   - 确认WebSocket连接状态

### 调试方法

1. **前端调试**
   - 打开浏览器开发者工具
   - 查看Console日志
   - 检查Network面板

2. **后端调试**
   - 查看后端日志输出
   - 检查WebSocket连接状态
   - 监控音频数据处理

## 总结

前端录音 + 后端STT处理模式提供了更灵活的用户体验，用户可以在自己的设备上进行录音，同时享受后端强大的STT处理能力。这种架构既保证了用户体验，又充分利用了后端服务的优势。
