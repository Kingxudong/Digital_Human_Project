# AI对话系统详细流程图

本目录包含了AI对话系统的详细流程图，展示了后端服务器的完整架构和函数调用关系。

## 文件说明

### 1. system_flow_diagram.png
- **格式**: PNG图片
- **大小**: 179KB
- **分辨率**: 高分辨率（300 DPI）
- **用途**: 用于文档、演示或打印
- **内容**: 完整的系统流程图，包含所有函数调用关系

### 2. system_flow_diagram.html
- **格式**: HTML文件
- **大小**: 6.8KB
- **用途**: 交互式查看流程图
- **特性**: 
  - 支持缩放和平移
  - 包含下载链接
  - 响应式设计
  - 颜色编码说明

### 3. system_flow_diagram.mmd
- **格式**: Mermaid源码文件
- **大小**: 4.4KB
- **用途**: 可编辑的流程图源码
- **特性**: 
  - 可在Mermaid在线编辑器中编辑
  - 支持版本控制
  - 可导出为多种格式

## 流程图内容

### 主要流程模块

1. **系统启动流程**
   - `startup_event()` - 系统初始化
   - 各客户端初始化
   - WebSocket服务器启动

2. **数字人管理流程**
   - `join_room()` - 加入房间
   - `leave_room()` - 离开房间
   - 连接管理和健康检查

3. **流式查询处理流程**
   - `process_query_stream()` - 主处理函数
   - `stream_pipeline()` - 流式处理管道
   - LLM → TTS → 数字人完整流程

4. **语音控制流程**
   - `single_button_voice_control()` - 单按钮语音控制
   - `record_and_process_voice()` - 录音处理
   - ASR语音识别

5. **WebSocket音频处理流程**
   - `websocket_handler()` - WebSocket处理器
   - `handle_audio_data()` - 音频数据处理
   - 实时STT识别

6. **系统管理流程**
   - `reset_connections()` - 连接重置
   - `get_connection_status()` - 状态检查
   - `cleanup_pending_requests()` - 清理任务

### 颜色编码

- **蓝色**: 系统启动和清理任务
- **紫色**: 主要处理函数
- **橙色**: 决策判断点
- **红色**: 错误处理
- **绿色**: 客户端操作

## 使用方法

### 查看流程图

1. **PNG图片**: 直接打开查看，适合文档和演示
2. **HTML文件**: 在浏览器中打开，支持交互式查看
3. **Mermaid源码**: 在Mermaid在线编辑器中编辑

### 在线编辑器

可以使用以下在线工具编辑Mermaid源码：
- [Mermaid Live Editor](https://mermaid.live/)
- [Mermaid Chart](https://www.mermaidchart.com/)

### 导出其他格式

从Mermaid源码可以导出为：
- SVG
- PNG
- PDF
- 其他格式

## 技术架构

### 核心组件

1. **LLM客户端**: 处理大语言模型对话
2. **TTS客户端**: 文本转语音服务
3. **数字人客户端**: 虚拟形象驱动
4. **STT客户端**: 语音转文本服务
5. **WebSocket服务器**: 实时音频处理

### 数据流

1. **文本对话流**: 用户输入 → LLM → TTS → 数字人
2. **语音对话流**: 用户语音 → ASR → LLM → TTS → 数字人
3. **实时音频流**: 前端录音 → WebSocket → STT → 实时识别

### 错误处理

- HTTP异常处理
- 参数验证错误处理
- 一般异常处理
- 连接重试机制
- 会话状态管理

## 维护说明

### 更新流程图

1. 修改 `system_flow_diagram.mmd` 文件
2. 使用Mermaid工具重新生成PNG
3. 更新HTML文件中的Mermaid代码

### 版本控制

- 将 `.mmd` 文件纳入版本控制
- PNG和HTML文件可以重新生成
- 保持流程图与代码同步

## 联系信息

如有问题或建议，请联系开发团队。
