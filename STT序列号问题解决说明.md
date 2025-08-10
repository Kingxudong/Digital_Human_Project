# STT序列号问题解决说明

## 问题描述

在使用STT服务进行语音识别时，出现了以下错误：

```
STT Error 45000000: {'error': 'decode ws request failed: unable to decode V1 protocol message: autoAssignedSequence (1) mismatch sequence in request (2)'}
```

这个错误表明在WebSocket协议中，序列号不匹配。服务器期望的序列号是1，但收到的请求序列号是2。

## 问题原因

1. **序列号管理不当**: 在发送音频数据时，序列号的递增时机不正确
2. **并发问题**: 多个请求同时发送时，序列号可能被重复使用
3. **初始化问题**: 序列号没有在每次会话开始时正确重置为1

## 解决方案

### 1. 添加序列号锁

```python
# 在STTClient初始化时添加序列号锁
self._seq_lock = asyncio.Lock()
```

### 2. 修复序列号递增逻辑

```python
async def send_audio(self, audio_data: bytes, is_last: bool = False) -> bool:
    async with self._seq_lock:  # 使用序列号锁确保线程安全
        try:
            # 构建音频请求 - 使用当前序列号
            current_seq = self.seq
            request = RequestBuilder.new_audio_only_request(current_seq, audio_data, is_last)
            await self.websocket.send(request)
            
            # 只有在成功发送后才增加序列号
            self.seq += 1
            logger.debug(f"Sent audio with seq: {current_seq}, is_last: {is_last}")
            return True
        except Exception as e:
            logger.error(f"Failed to send audio to STT: {e}")
            return False
```

### 3. 确保序列号从1开始

```python
async def start_recognition(self, ...):
    # 重置序列号为1，确保从1开始
    self.seq = 1
    logger.info(f"STT recognition started for session: {session_id} with seq: {self.seq}")
```

### 4. 修复完整客户端请求的序列号

```python
async def _send_full_client_request(self):
    async with self._seq_lock:  # 使用序列号锁确保线程安全
        current_seq = self.seq
        request = RequestBuilder.new_full_client_request(current_seq, self.config)
        self.seq += 1
        await self.websocket.send(request)
        logger.info(f"Sent full client request with seq: {current_seq}")
```

## 修复的文件

1. **python_sdk/stt_client.py**
   - 添加了序列号锁 `_seq_lock`
   - 修复了 `send_audio` 方法的序列号处理
   - 修复了 `_send_full_client_request` 方法的序列号处理
   - 在 `start_recognition` 中重置序列号为1

2. **python_sdk/backend_server.py**
   - 在STT启动端点中添加了序列号日志记录

## 测试验证

创建了测试脚本来验证修复：

1. **python_sdk/simple_stt_test.py** - 简单测试
2. **python_sdk/test_stt_sequence.py** - 详细序列号测试

## 关键改进点

### 1. 线程安全
- 使用 `asyncio.Lock()` 确保序列号的原子操作
- 防止并发请求导致的序列号冲突

### 2. 正确的序列号管理
- 在发送前获取当前序列号
- 只有在成功发送后才递增序列号
- 每次会话开始时重置序列号为1

### 3. 详细的日志记录
- 记录每次发送的序列号
- 便于调试和问题追踪

## 预期效果

修复后，STT服务应该能够：

1. ✅ 正确管理序列号，从1开始递增
2. ✅ 避免序列号冲突和重复
3. ✅ 支持并发音频数据发送
4. ✅ 提供详细的调试信息

## 使用建议

1. **重启服务**: 应用修复后，请重启后端服务
2. **测试验证**: 使用测试脚本验证修复效果
3. **监控日志**: 关注序列号相关的日志信息
4. **错误处理**: 如果仍有问题，检查网络连接和API密钥

## 总结

通过添加序列号锁、修复序列号递增逻辑、确保正确初始化，我们解决了STT服务中的序列号不匹配问题。这些修复确保了WebSocket协议的正确实现，提高了STT服务的稳定性和可靠性。 