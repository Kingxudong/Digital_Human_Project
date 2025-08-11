# WebSocket集成使用说明

## 概述

我们已经成功为数字人项目集成了WebSocket实时音频传输功能，实现了本地音频采集、处理和实时传输到服务器的完整流程。

## 系统架构

```
本地设备 → 音频采集 → 音频处理 → WebSocket传输 → 服务器识别 → 返回结果
```

### 核心组件

1. **音频采集器** (AudioCapture) - 使用 SoundDevice 本地录音
2. **音频处理器** (AudioProcessor) - Opus编码和音频优化
3. **WebSocket客户端** (AudioWebSocketClient) - 实时数据传输
4. **实时音频系统** (RealtimeAudioSystem) - 统一管理系统
5. **后端WebSocket服务器** - 接收和处理音频数据

## 文件结构

```
develop/python_sdk/
├── audio_config.py              # 音频配置常量
├── audio_capture.py             # 改进的音频采集器
├── audio_processor.py           # 改进的音频处理器
├── audio_websocket_client.py    # WebSocket客户端
├── realtime_audio_system.py     # 实时音频传输系统
├── backend_server.py            # 后端服务器（已集成WebSocket）
├── test_realtime_audio_system.py # 测试脚本
└── WebSocket集成使用说明.md     # 本文档
```

## 安装依赖

确保安装了必要的依赖包：

```bash
cd develop/python_sdk
pip install websockets sounddevice opuslib soxr numpy
```

## 使用方法

### 1. 启动WebSocket服务器

有两种方式启动WebSocket服务器：

#### 方式一：独立WebSocket服务器（推荐）

```bash
cd develop/python_sdk
python websocket_server.py
```

这将启动独立的WebSocket服务器：
- WebSocket: `ws://localhost:9001/audio`

#### 方式二：集成到后端服务器

```bash
cd develop/python_sdk
python backend_server.py
```

这将启动完整的后端服务：
- HTTP API: `http://localhost:9000`
- WebSocket: `ws://localhost:9001/audio`

**注意**：如果遇到WebSocket启动问题，建议使用方式一（独立服务器）。

### 2. 使用实时音频系统

#### 基本使用

```python
import asyncio
from realtime_audio_system import RealtimeAudioSystem

async def main():
    # 创建实时音频系统
    system = RealtimeAudioSystem(
        websocket_url="ws://localhost:9001/audio",
        session_id="my_session_001",
        auto_reconnect=True,
        enable_audio_processing=True,
        enable_transmission=True
    )
    
    # 设置回调函数
    system.on_stt_result = handle_stt_result
    system.on_error = handle_error
    
    try:
        # 初始化系统
        await system.initialize()
        
        # 启动系统
        await system.start()
        
        # 运行一段时间
        await asyncio.sleep(60)
        
    finally:
        # 停止系统
        await system.stop()
        await system.close()

async def handle_stt_result(text: str, is_final: bool, confidence: float):
    """处理STT结果"""
    print(f"识别结果: {text} (最终: {is_final}, 置信度: {confidence:.2f})")

async def handle_error(error: str):
    """处理错误"""
    print(f"系统错误: {error}")

if __name__ == "__main__":
    asyncio.run(main())
```

#### 高级配置

```python
# 创建自定义配置的系统
system = RealtimeAudioSystem(
    websocket_url="ws://localhost:9001/audio",
    session_id="custom_session",
    auto_reconnect=True,
    enable_audio_processing=True,  # 启用Opus编码
    enable_transmission=True       # 启用WebSocket传输
)

# 设置更多回调
system.on_system_state_change = handle_state_change
system.on_audio_quality_change = handle_quality_change
system.on_stt_result = handle_stt_result
system.on_error = handle_error

async def handle_state_change(old_state, new_state):
    print(f"系统状态: {old_state.value} -> {new_state.value}")

async def handle_quality_change(quality_score: float):
    print(f"音频质量: {quality_score:.3f}")
```

### 3. 单独使用组件

#### 音频采集器

```python
import asyncio
from audio_capture import AudioCapture

async def main():
    capture = AudioCapture(
        sample_rate=16000,
        channels=1,
        frame_duration_ms=20,
        silence_threshold=0.005
    )
    
    # 设置回调
    capture.on_audio_data = handle_audio_data
    capture.on_silence_detected = handle_silence
    
    await capture.initialize()
    await capture.start_recording()
    
    # 运行...
    await asyncio.sleep(10)
    
    capture.stop_recording()
    capture.close()

async def handle_audio_data(audio_data: bytes):
    print(f"收到音频数据: {len(audio_data)} 字节")

async def handle_silence(silence_duration: float):
    print(f"检测到静音: {silence_duration:.2f}秒")
```

#### WebSocket客户端

```python
import asyncio
from audio_websocket_client import AudioWebSocketClient

async def main():
    client = AudioWebSocketClient(
        server_url="ws://localhost:9001/audio",
        session_id="test_session",
        auto_reconnect=True
    )
    
    # 设置回调
    client.on_connected = handle_connected
    client.on_stt_result = handle_stt_result
    
    await client.connect()
    
    # 发送音频数据
    audio_data = b"test_audio_data"
    await client.send_audio_data(audio_data)
    
    # 运行...
    await asyncio.sleep(10)
    
    await client.disconnect()

async def handle_connected():
    print("WebSocket连接成功")

async def handle_stt_result(stt_result: dict):
    print(f"STT结果: {stt_result}")
```

## 测试

### 1. 测试WebSocket连接

#### 步骤1：使用简化服务器测试

```bash
cd develop/python_sdk
python simple_websocket_server.py
```

在另一个终端运行：
```bash
python simple_websocket_client.py
```

#### 步骤2：使用完整服务器测试

```bash
cd develop/python_sdk
python websocket_server.py
```

在另一个终端运行：
```bash
python test_websocket_debug.py
```

#### 步骤3：使用原始测试脚本

```bash
cd develop/python_sdk
python test_websocket_fix.py
```

**注意**：如果遇到WebSocket错误1011（内部错误），请按顺序执行上述步骤进行调试。

### 2. 运行集成测试

```bash
cd develop/python_sdk
python test_realtime_audio_system.py
```

### 3. 使用WebSocket测试工具

也可以使用在线WebSocket测试工具连接到：
```
ws://localhost:9001/audio
```

### 3. 监控系统状态

```python
# 获取系统统计信息
stats = system.get_statistics()
print(f"系统统计: {stats}")

# 检查系统健康状态
is_healthy = system.is_healthy()
print(f"系统健康: {is_healthy}")
```

## 配置参数

### 音频采集器配置

```python
AudioCapture(
    sample_rate=16000,        # 采样率
    channels=1,               # 声道数
    frame_duration_ms=20,     # 帧长度（毫秒）
    device_id=None,           # 音频设备ID（None为自动选择）
    buffer_size=1000,         # 缓冲区大小
    silence_threshold=0.005   # 静音检测阈值
)
```

### 音频处理器配置

```python
AudioProcessor(
    input_sample_rate=16000,   # 输入采样率
    output_sample_rate=16000,  # 输出采样率
    channels=1,                # 声道数
    frame_duration_ms=20,      # 帧长度
    bitrate=64000,             # Opus编码比特率
    complexity=5               # 编码复杂度
)
```

### WebSocket客户端配置

```python
AudioWebSocketClient(
    server_url="ws://localhost:9001/audio",  # 服务器地址
    session_id=None,                         # 会话ID（None为自动生成）
    auto_reconnect=True,                     # 自动重连
    reconnect_interval=5.0,                  # 重连间隔
    max_reconnect_attempts=10,               # 最大重连次数
    heartbeat_interval=30.0                  # 心跳间隔
)
```

## 错误处理

### 常见错误及解决方案

1. **音频设备错误**
   ```
   错误: 没有找到可用的音频输入设备
   解决: 检查麦克风权限和连接状态
   ```

2. **WebSocket连接失败**
   ```
   错误: WebSocket连接失败
   解决: 确保后端服务器正在运行
   ```

3. **WebSocket错误1011（内部错误）**
   ```
   错误: received 1011 (internal error)
   解决: 使用修复后的服务器和客户端代码
   ```

3. **音频处理错误**
   ```
   错误: Opus编码器初始化失败
   解决: 检查opuslib库安装
   ```

### 错误回调处理

```python
async def handle_error(error: str):
    """统一错误处理"""
    logger.error(f"系统错误: {error}")
    
    # 根据错误类型采取相应措施
    if "音频设备" in error:
        # 尝试重新初始化音频设备
        pass
    elif "WebSocket" in error:
        # 尝试重新连接
        pass
    elif "编码器" in error:
        # 尝试重新初始化处理器
        pass
```

## 性能优化

### 1. 音频质量优化

- 调整静音检测阈值
- 优化Opus编码参数
- 监控音频质量评分

### 2. 网络传输优化

- 调整缓冲区大小
- 优化心跳间隔
- 监控传输延迟

### 3. 系统监控

```python
# 定期检查系统状态
async def monitor_system():
    while True:
        stats = system.get_statistics()
        
        # 检查音频质量
        if stats["audio_quality_score"] < 0.8:
            logger.warning("音频质量较低")
            
        # 检查传输延迟
        if stats["transmission_latency"] > 100:
            logger.warning("传输延迟较高")
            
        await asyncio.sleep(5)
```

## 扩展功能

### 1. 添加自定义音频处理

```python
class CustomAudioProcessor(AudioProcessor):
    def process_audio_chunk(self, audio_chunk: bytes) -> Optional[bytes]:
        # 自定义音频处理逻辑
        processed_data = super().process_audio_chunk(audio_chunk)
        
        # 添加自定义处理
        if processed_data:
            # 进行额外处理
            pass
            
        return processed_data
```

### 2. 集成到现有系统

```python
# 在现有的数字人系统中集成
class DigitalHumanSystem:
    def __init__(self):
        self.audio_system = RealtimeAudioSystem()
        self.llm_client = LLMClient()
        self.tts_client = TTSClient()
        
    async def start_voice_interaction(self):
        # 启动语音交互
        self.audio_system.on_stt_result = self.handle_user_input
        await self.audio_system.start()
        
    async def handle_user_input(self, text: str, is_final: bool, confidence: float):
        if is_final:
            # 处理用户输入
            response = await self.llm_client.chat(text)
            audio = await self.tts_client.synthesize(response)
            # 播放音频响应
```

## 总结

通过WebSocket集成，我们成功实现了：

1. **本地音频采集** - 解决了服务器音频硬件依赖问题
2. **实时音频处理** - 高效的Opus编码和音频优化
3. **实时数据传输** - 基于WebSocket的可靠传输
4. **完整的错误处理** - 自动重连和错误恢复
5. **系统监控** - 全面的性能和质量监控

这个集成为数字人项目提供了稳定、高效的实时音频处理基础，支持后续的语音识别、自然语言处理和语音合成功能扩展。
