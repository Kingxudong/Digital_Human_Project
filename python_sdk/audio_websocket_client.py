#!/usr/bin/env python3
"""
改进的WebSocket客户端 - 参考小智项目实现
提供稳定的实时音频传输功能
"""

import asyncio
import json
import logging
import time
import websockets
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSING = "closing"


@dataclass
class AudioFrame:
    """音频帧数据结构"""
    data: bytes
    timestamp: float
    sequence: int


class AudioWebSocketClient:
    """
    改进的WebSocket客户端 - 参考小智项目实现
    """
    
    def __init__(self, server_url: str = "ws://localhost:9002/audio"):
        self.server_url = server_url
        self.websocket = None
        self.state = ConnectionState.DISCONNECTED
        
        # 连接参数 - 参考小智项目
        self.ping_interval = 20.0  # 心跳间隔20秒
        self.ping_timeout = 20.0   # ping超时20秒
        self.close_timeout = 10.0  # 关闭超时10秒
        self.max_size = 10 * 1024 * 1024  # 最大消息10MB
        
        # 连接管理
        self._is_closing = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._auto_reconnect_enabled = True
        
        # 消息处理
        self._message_task = None
        self._heartbeat_task = None
        self._connection_monitor_task = None
        
        # 音频数据管理
        self._audio_queue = deque(maxlen=1000)  # 音频数据队列
        self._sequence_counter = 0
        
        # 回调函数
        self._on_connected: Optional[Callable] = None
        self._on_disconnected: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._on_message: Optional[Callable] = None
        self._on_stt_result: Optional[Callable] = None
        
        # 连接状态事件
        self._hello_received = None
        
        # 统计信息
        self._stats = {
            "sent_frames": 0,
            "sent_bytes": 0,
            "received_messages": 0,
            "connection_time": None,
            "last_activity": None
        }
    
    def set_callbacks(self, 
                     on_connected: Optional[Callable] = None,
                     on_disconnected: Optional[Callable] = None,
                     on_error: Optional[Callable] = None,
                     on_message: Optional[Callable] = None,
                     on_stt_result: Optional[Callable] = None):
        """设置回调函数"""
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._on_message = on_message
        self._on_stt_result = on_stt_result
    
    async def connect(self) -> bool:
        """连接到WebSocket服务器 - 参考小智项目实现"""
        if self._is_closing:
            logger.warning("连接正在关闭中，取消新的连接尝试")
            return False
        
        try:
            self.state = ConnectionState.CONNECTING
            logger.info(f"正在连接到 {self.server_url}")
            
            # 创建hello接收事件
            self._hello_received = asyncio.Event()
            
            # 建立WebSocket连接 - 参考小智项目的连接参数
            self.websocket = await websockets.connect(
                uri=self.server_url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                close_timeout=self.close_timeout,
                max_size=self.max_size,
                compression=None,  # 禁用压缩以提高稳定性
            )
            
            # 启动消息处理任务
            self._message_task = asyncio.create_task(self._message_handler())
            
            # 启动连接监控
            self._start_connection_monitor()
            
            # 发送客户端hello消息 - 参考小智项目的握手协议
            hello_message = {
                "type": "hello",
                "version": 1,
                "features": {
                    "audio": True,
                    "stt": True,
                },
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 20,
                },
            }
            await self.send_json(hello_message)
            
            # 等待服务器hello响应
            try:
                await asyncio.wait_for(self._hello_received.wait(), timeout=10.0)
                self.state = ConnectionState.CONNECTED
                self._reconnect_attempts = 0
                self._stats["connection_time"] = time.time()
                self._stats["last_activity"] = time.time()
                
                logger.info("WebSocket连接成功")
                
                # 调用连接成功回调
                if self._on_connected:
                    try:
                        await self._on_connected()
                    except Exception as e:
                        logger.error(f"连接成功回调执行失败: {e}")
                
                return True
                
            except asyncio.TimeoutError:
                logger.error("等待服务器hello响应超时")
                await self._cleanup_connection()
                return False
                
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            await self._cleanup_connection()
            return False
    
    async def disconnect(self):
        """断开WebSocket连接"""
        self._is_closing = True
        self.state = ConnectionState.CLOSING
        
        try:
            await self._cleanup_connection()
            logger.info("WebSocket连接已断开")
        except Exception as e:
            logger.error(f"断开连接时出错: {e}")
        finally:
            self._is_closing = False
    
    async def send_json(self, data: Dict[str, Any]) -> bool:
        """发送JSON消息"""
        if not self.websocket or self.state != ConnectionState.CONNECTED:
            logger.warning("WebSocket未连接，无法发送JSON消息")
            return False
        
        try:
            message = json.dumps(data, ensure_ascii=False)
            await self.websocket.send(message)
            self._stats["last_activity"] = time.time()
            logger.debug(f"发送JSON消息: {data.get('type', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"发送JSON消息失败: {e}")
            await self._handle_connection_loss(f"发送JSON失败: {str(e)}")
            return False
    
    async def send_audio_data(self, audio_data: bytes) -> bool:
        """发送音频数据 - 参考小智项目的音频发送方式"""
        if not self.websocket or self.state != ConnectionState.CONNECTED:
            logger.warning("WebSocket未连接，无法发送音频数据")
            return False
        
        try:
            # 直接发送二进制音频数据，不发送元数据
            await self.websocket.send(audio_data)
            
            # 更新统计信息
            self._stats["sent_frames"] += 1
            self._stats["sent_bytes"] += len(audio_data)
            self._stats["last_activity"] = time.time()
            
            return True
            
        except websockets.ConnectionClosed as e:
            logger.warning(f"发送音频时连接已关闭: {e}")
            await self._handle_connection_loss(f"发送音频失败: {e.code} {e.reason}")
            return False
        except Exception as e:
            logger.error(f"发送音频数据失败: {e}")
            await self._handle_connection_loss(f"发送音频异常: {str(e)}")
            return False
    
    async def _message_handler(self):
        """消息处理循环 - 参考小智项目的消息处理"""
        try:
            async for message in self.websocket:
                if self._is_closing:
                    break
                
                try:
                    self._stats["received_messages"] += 1
                    self._stats["last_activity"] = time.time()
                    
                    if isinstance(message, str):
                        await self._handle_text_message(message)
                    elif isinstance(message, bytes):
                        await self._handle_binary_message(message)
                        
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")
                    continue
                    
        except websockets.ConnectionClosed as e:
            if not self._is_closing:
                logger.info(f"WebSocket连接已关闭: {e}")
                await self._handle_connection_loss(f"连接关闭: {e.code} {e.reason}")
        except websockets.ConnectionClosedError as e:
            if not self._is_closing:
                logger.info(f"WebSocket连接错误关闭: {e}")
                await self._handle_connection_loss(f"连接错误: {e.code} {e.reason}")
        except Exception as e:
            logger.error(f"消息处理循环异常: {e}")
            await self._handle_connection_loss(f"消息处理异常: {str(e)}")
    
    async def _handle_text_message(self, message: str):
        """处理文本消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "hello":
                # 处理服务器hello响应
                await self._handle_server_hello(data)
            elif msg_type == "stt_result":
                # 处理STT结果
                if self._on_stt_result:
                    try:
                        await self._on_stt_result(data)
                    except Exception as e:
                        logger.error(f"STT结果回调执行失败: {e}")
            else:
                # 其他消息类型
                if self._on_message:
                    try:
                        await self._on_message(data)
                    except Exception as e:
                        logger.error(f"消息回调执行失败: {e}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"无效的JSON消息: {message}, 错误: {e}")
        except Exception as e:
            logger.error(f"处理文本消息时出错: {e}")
    
    async def _handle_binary_message(self, message: bytes):
        """处理二进制消息"""
        logger.debug(f"收到二进制消息: {len(message)} 字节")
        # 这里可以处理服务器返回的音频数据等
    
    async def _handle_server_hello(self, data: dict):
        """处理服务器hello响应 - 参考小智项目"""
        try:
            # 验证传输方式
            transport = data.get("transport")
            if not transport or transport != "websocket":
                logger.error(f"不支持的传输方式: {transport}")
                return
            
            logger.info("收到服务器hello响应")
            print("服务器返回初始化配置:", data)
            
            # 设置hello接收事件
            self._hello_received.set()
            
        except Exception as e:
            logger.error(f"处理服务器hello响应时出错: {e}")
    
    def _start_connection_monitor(self):
        """启动连接监控任务"""
        if (self._connection_monitor_task is None or 
            self._connection_monitor_task.done()):
            self._connection_monitor_task = asyncio.create_task(
                self._connection_monitor()
            )
    
    async def _connection_monitor(self):
        """连接健康状态监控"""
        try:
            while self.websocket and not self._is_closing:
                await asyncio.sleep(5)  # 每5秒检查一次
                
                # 检查连接状态
                if self.websocket and self.websocket.closed:
                    logger.warning("检测到WebSocket连接已关闭")
                    await self._handle_connection_loss("连接已关闭")
                    break
                    
        except asyncio.CancelledError:
            logger.debug("连接监控任务被取消")
        except Exception as e:
            logger.error(f"连接监控异常: {e}")
    
    async def _handle_connection_loss(self, reason: str):
        """处理连接丢失"""
        logger.warning(f"连接丢失: {reason}")
        
        # 更新连接状态
        was_connected = self.state == ConnectionState.CONNECTED
        self.state = ConnectionState.DISCONNECTED
        
        # 调用断开连接回调
        if self._on_disconnected and was_connected:
            try:
                await self._on_disconnected(reason)
            except Exception as e:
                logger.error(f"断开连接回调执行失败: {e}")
        
        # 清理连接
        await self._cleanup_connection()
        
        # 自动重连
        if (not self._is_closing and 
            self._auto_reconnect_enabled and 
            self._reconnect_attempts < self._max_reconnect_attempts):
            await self._attempt_reconnect(reason)
        else:
            # 调用错误回调
            if self._on_error:
                try:
                    await self._on_error(reason)
                except Exception as e:
                    logger.error(f"错误回调执行失败: {e}")
    
    async def _attempt_reconnect(self, original_reason: str):
        """尝试自动重连"""
        self._reconnect_attempts += 1
        logger.info(f"尝试自动重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
        
        # 等待一段时间后重连
        await asyncio.sleep(min(self._reconnect_attempts * 2, 30))
        
        try:
            success = await self.connect()
            if success:
                logger.info("自动重连成功")
            else:
                logger.warning(f"自动重连失败 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
        except Exception as e:
            logger.error(f"重连过程中出错: {e}")
    
    async def _cleanup_connection(self):
        """清理连接相关资源"""
        self.state = ConnectionState.DISCONNECTED
        
        # 取消消息处理任务
        if self._message_task and not self._message_task.done():
            self._message_task.cancel()
            try:
                await self._message_task
            except asyncio.CancelledError:
                pass
        
        # 取消连接监控任务
        if (self._connection_monitor_task and 
            not self._connection_monitor_task.done()):
            self._connection_monitor_task.cancel()
            try:
                await self._connection_monitor_task
            except asyncio.CancelledError:
                pass
        
        # 关闭WebSocket连接
        if self.websocket:
            try:
                # 检查连接状态
                try:
                    if not self.websocket.closed:
                        await self.websocket.close()
                except AttributeError:
                    # 如果websocket对象没有closed属性，尝试其他方法
                    try:
                        if self.websocket.state.name != "CLOSED":
                            await self.websocket.close()
                    except AttributeError:
                        # 如果无法检查状态，直接尝试关闭
                        await self.websocket.close()
            except Exception as e:
                logger.error(f"关闭WebSocket连接时出错: {e}")
        
        self.websocket = None
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        if not (self.state == ConnectionState.CONNECTED and self.websocket):
            return False
        
        # 检查WebSocket连接状态
        try:
            return not self.websocket.closed
        except AttributeError:
            # 如果websocket对象没有closed属性，尝试其他方法
            try:
                return self.websocket.state.name == "OPEN"
            except AttributeError:
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        stats["state"] = self.state.value
        stats["reconnect_attempts"] = self._reconnect_attempts
        stats["auto_reconnect_enabled"] = self._auto_reconnect_enabled
        return stats
    
    def enable_auto_reconnect(self, enabled: bool = True, max_attempts: int = 5):
        """启用或禁用自动重连"""
        self._auto_reconnect_enabled = enabled
        self._max_reconnect_attempts = max_attempts if enabled else 0
        logger.info(f"{'启用' if enabled else '禁用'}自动重连，最大尝试次数: {max_attempts}")