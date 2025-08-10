"""Digital Human Client for avatar live streaming functionality."""

import json
import asyncio
import websockets
import base64
import ssl
from typing import Dict, Any, Optional, Callable, Union
from enum import Enum
from exceptions import DigitalHumanError
from loguru import logger


class AvatarType(Enum):
    """Avatar types."""
    PIC = "pic"  # Single image avatar
    THREE_MIN = "3min"  # 3-minute cloned avatar


class InputMode(Enum):
    """Input modes for avatar driving."""
    AUDIO = "audio"  # Audio-driven


class StreamingType(Enum):
    """Streaming types."""
    RTMP = "rtmp"  # RTMP streaming
    BYTERTC = "bytertc"  # ByteRTC streaming


class DigitalHumanClient:
    """Client for Digital Human avatar live streaming."""
    
    def __init__(self, appid: str, token: str, verify_ssl: bool = True):
        """
        Initialize Digital Human client.
        
        Args:
            appid: Digital human account ID
            token: Digital human account token
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.appid = appid
        self.token = token
        self.verify_ssl = verify_ssl
        self.websocket = None
        self.live_id = None
        
    def _create_message(self, header: str, body: Union[str, Dict[str, Any]]) -> str:
        """Create a message with header and body."""
        if isinstance(body, dict):
            body = json.dumps(body)
        return f"{header}{body}"
    
    async def connect(self) -> bool:
        """Connect to Digital Human WebSocket service."""
        uri = "wss://openspeech.bytedance.com/virtual_human/avatar_live/live"
        
        # Try multiple connection strategies
        connection_strategies = [
            {"verify_ssl": True, "timeout": 25.0},   # Strategy 1: SSL verification with longer timeout
            {"verify_ssl": False, "timeout": 25.0},  # Strategy 2: No SSL verification with longer timeout
            {"verify_ssl": False, "timeout": 35.0},  # Strategy 3: No SSL verification with extended timeout
        ]
        
        last_error = None
        
        for i, strategy in enumerate(connection_strategies):
            try:
                logger.info(f"Connection attempt {i+1}/{len(connection_strategies)} with strategy: {strategy}")
                
                # WebSocket connection parameters with more stable settings
                connect_kwargs = {
                    "ping_interval": 25,  # Increased for more stable connection
                    "ping_timeout": 15,   # Increased for more tolerance
                    "close_timeout": 15,  # Increased for more tolerance
                    "max_size": 2**23,    # 8MB max message size
                    "compression": None,  # Disable compression for better performance
                    "max_queue": 32,      # Increase message queue size
                }
                
                if strategy["verify_ssl"]:
                    self.websocket = await asyncio.wait_for(
                        websockets.connect(uri, **connect_kwargs),
                        timeout=strategy["timeout"]
                    )
                else:
                    # Create SSL context that doesn't verify certificates
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    connect_kwargs["ssl"] = ssl_context
                    
                    self.websocket = await asyncio.wait_for(
                        websockets.connect(uri, **connect_kwargs),
                        timeout=strategy["timeout"]
                    )
                
                # Verify connection is actually working
                if self.websocket and self.websocket.state == websockets.protocol.State.OPEN:
                    logger.info(f"Successfully connected to Digital Human WebSocket service using strategy {i+1}")
                    return True
                else:
                    raise DigitalHumanError("Connection established but not in OPEN state")
                    
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Connection attempt {i+1} timed out after {strategy['timeout']} seconds")
                if i < len(connection_strategies) - 1:
                    await asyncio.sleep(2)  # Wait before next attempt
                    
            except websockets.exceptions.InvalidStatusCode as e:
                last_error = e
                logger.warning(f"Connection attempt {i+1} failed with invalid status code: {e}")
                if i < len(connection_strategies) - 1:
                    await asyncio.sleep(2)
                    
            except websockets.exceptions.ConnectionClosed as e:
                last_error = e
                logger.warning(f"Connection attempt {i+1} failed during handshake: {e}")
                if i < len(connection_strategies) - 1:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Connection attempt {i+1} failed with error: {e}")
                if i < len(connection_strategies) - 1:
                    await asyncio.sleep(2)
        
        # All strategies failed
        if isinstance(last_error, asyncio.TimeoutError):
            raise DigitalHumanError("连接超时，请检查网络连接")
        elif isinstance(last_error, websockets.exceptions.InvalidStatusCode):
            raise DigitalHumanError("服务器响应异常，请稍后重试")
        elif isinstance(last_error, websockets.exceptions.ConnectionClosed):
            raise DigitalHumanError("连接握手失败，请检查网络设置")
        else:
            raise DigitalHumanError(f"连接失败: {str(last_error)}")
    
    async def start_live_rtmp(self, 
                             live_id: str,
                             avatar_type: AvatarType,
                             role: str,
                             rtmp_addr: str,
                             background: Optional[str] = None,
                             video_config: Optional[Dict[str, Any]] = None,
                             role_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start RTMP live streaming.
        
        Args:
            live_id: Unique live ID
            avatar_type: Type of avatar
            role: Avatar role/character ID
            rtmp_addr: RTMP streaming address
            background: Optional background URL
            video_config: Optional video configuration
            role_config: Optional role configuration
            
        Returns:
            Response data from server
        """
        streaming_config = {
            "type": "rtmp",
            "rtmp_addr": rtmp_addr
        }
        return await self._start_live_internal(live_id, avatar_type, role, streaming_config, background, video_config, role_config)
    
    async def start_live_rtc(self, 
                            live_id: str,
                            avatar_type: AvatarType,
                            role: str,
                            rtc_app_id: str,
                            rtc_room_id: str,
                            rtc_uid: str,
                            rtc_token: str,
                            background: Optional[str] = None,
                            video_config: Optional[Dict[str, Any]] = None,
                            role_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start ByteRTC live streaming.
        
        Args:
            live_id: Unique live ID
            avatar_type: Type of avatar
            role: Avatar role/character ID
            rtc_app_id: ByteRTC account ID
            rtc_room_id: ByteRTC room ID
            rtc_uid: ByteRTC streaming user ID
            rtc_token: ByteRTC streaming temporary token
            background: Optional background URL
            video_config: Optional video configuration
            role_config: Optional role configuration
            
        Returns:
            Response data from server
        """
        streaming_config = {
            "type": "bytertc",
            "rtc_app_id": rtc_app_id,
            "rtc_room_id": rtc_room_id,
            "rtc_uid": rtc_uid,
            "rtc_token": rtc_token
        }

        logger.info(f"Starting RTC live streaming on {live_id}")
        return await self._start_live_internal(live_id, avatar_type, role, streaming_config, background, video_config, role_config)
    
    async def _start_live_internal(self, 
                                  live_id: str,
                                  avatar_type: AvatarType,
                                  role: str,
                                  streaming_config: Dict[str, Any],
                                  background: Optional[str] = None,
                                  video_config: Optional[Dict[str, Any]] = None,
                                  role_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Internal method to start live streaming.
        
        Args:
            live_id: Unique live ID
            avatar_type: Type of avatar
            role: Avatar role/character ID
            streaming_config: Streaming configuration
            background: Optional background URL
            video_config: Optional video configuration
            role_config: Optional role configuration
            
        Returns:
            Response data from server
        """
        if not self.websocket:
            raise DigitalHumanError("未连接到服务器，请重新连接")
        
        self.live_id = live_id
        
        # Build initialization message
        init_data = {
            "live": {
                "live_id": live_id
            },
            "auth": {
                "appid": self.appid,  # Use api_key as appid
                "token": self.token   # Use api_key as token for now
            },
            "avatar": {
                "avatar_type": avatar_type.value,
                "input_mode": "audio",
                "role": role
            },
            "streaming": streaming_config
        }
        
        if background:
            init_data["avatar"]["background"] = background
        
        if video_config:
            init_data["video"] = video_config
        
        if role_config:
            init_data["avatar"]["role_conf"] = role_config
        
        # Send initialization message
        message = self._create_message("|CTL|00|", init_data)
        await self.websocket.send(message)
        logger.info(f"Sent initialization message for live_id: {live_id}")
        
        # Wait for confirmation with optimized timeout
        try:
            start_time = asyncio.get_event_loop().time()
            timeout = 20.0  # Reduced from 30 to 20 seconds for faster response
            
            while True:
                # Check timeout
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise asyncio.TimeoutError("Timeout waiting for server response")
                
                # Wait for response with remaining timeout
                remaining_timeout = timeout - (asyncio.get_event_loop().time() - start_time)
                response = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=remaining_timeout
                )
                logger.info(f"Received response: {response[:100]}...")  # Log first 100 chars
                
                if response.startswith("|MSG|00|"):
                    # Success response
                    body = response[8:]  # Remove header
                    try:
                        result = json.loads(body)
                        if result.get("code") == 1000:
                            logger.info(f"Digital human live streaming started successfully: {live_id}")
                            return {
                                "live_id": live_id,
                                "status": "success",
                                "message": result.get("message", "success")
                            }
                        else:
                            error_code = result.get("code")
                            error_message = result.get("message", "Unknown error")
                            raise DigitalHumanError(f"Failed to start live: {error_message} (code: {error_code})")
                    except json.JSONDecodeError as e:
                        raise DigitalHumanError(f"Invalid response format: {e}")
                
                elif response.startswith("|MSG|02|"):
                    # Heartbeat message - ignore and continue waiting
                    logger.debug("Received heartbeat message, continuing to wait for response")
                    continue
                
                elif response.startswith("|MSG|01|"):
                    # Error notification
                    body = response[8:]  # Remove header
                    try:
                        data = json.loads(body)
                        error_code = data.get("code")
                        error_message = data.get("message", "Unknown error")
                        raise DigitalHumanError(f"Server error: {error_message} (code: {error_code})")
                    except json.JSONDecodeError as e:
                        raise DigitalHumanError(f"Invalid error response format: {e}")
                
                else:
                    # Unexpected response format - log more details for debugging
                    logger.warning(f"Unexpected response format: {response[:200]}")
                    logger.warning(f"Response length: {len(response)}")
                    logger.warning(f"Response type: {type(response)}")
                    raise DigitalHumanError(f"Unexpected response format: {response[:100]}")
                
        except asyncio.TimeoutError:
            raise DigitalHumanError("服务器响应超时，请稍后重试")
        except websockets.exceptions.ConnectionClosed as e:
            raise DigitalHumanError("连接已断开，请重新连接")
    
    async def drive_with_audio_url(self, audio_url: str, audio_format: str = "wav") -> None:
        """
        Drive avatar with audio URL.
        
        Args:
            audio_url: URL of the audio file
            audio_format: Audio format (wav, mp3, pcm)
        """
        if not self.websocket:
            raise DigitalHumanError("Not connected to WebSocket")
        
        ssml = f'<speak><audio url="{audio_url}" format="{audio_format}"/></speak>'
        message = self._create_message("|DAT|01|", ssml)
        await self.websocket.send(message)
    
    async def drive_with_streaming_audio(self, audio_data: bytes) -> None:
        """
        Drive avatar with streaming audio data.
        
        Args:
            audio_data: PCM audio data (16kHz, mono, 16-bit)
        """
        if not self.websocket:
            raise DigitalHumanError("Not connected to WebSocket")
        
        # Send binary audio data with header
        header = b"|DAT|02|"
        message = header + audio_data
        await self.websocket.send(message)
    
    async def drive_with_structured_audio(self, audio_data: bytes, extra_data: Optional[str] = None) -> None:
        """
        Drive avatar with structured streaming audio.
        
        Args:
            audio_data: PCM audio data (16kHz, mono, 16-bit)
            extra_data: Optional custom data (max 4kB)
        """
        if not self.websocket:
            raise DigitalHumanError("Not connected to WebSocket")
        
        audio_b64 = base64.b64encode(audio_data).decode('utf-8')
        
        structured_data = {
            "audio": audio_b64
        }
        
        if extra_data:
            structured_data["extra_data"] = extra_data
        
        message = self._create_message("|DAT|04|", structured_data)
        await self.websocket.send(message)
    
    async def finish_streaming_audio(self) -> None:
        """Finish streaming audio input."""
        if not self.websocket:
            raise DigitalHumanError("Not connected to WebSocket")
        
        try:
            message = "|CTL|12|"
            await self.websocket.send(message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Connection closed while finishing streaming audio: {e}")
            # Don't raise error, just log it
        except Exception as e:
            logger.error(f"Error finishing streaming audio: {e}")
            raise DigitalHumanError(f"Failed to finish streaming audio: {e}")
    
    async def interrupt_playback(self) -> None:
        """Interrupt current playback and enter silent state."""
        if not self.websocket:
            raise DigitalHumanError("Not connected to WebSocket")
        
        message = "|CTL|03|"
        await self.websocket.send(message)
    
    async def listen_events(self, 
                           on_status: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                           on_error: Optional[Callable[[int, str], None]] = None) -> None:
        """
        Listen for avatar events.
        
        Args:
            on_status: Callback for status events
            on_error: Callback for error events
        """
        if not self.websocket:
            raise DigitalHumanError("Not connected to WebSocket")
        
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    if message.startswith("|DAT|02|"):
                        # Status event
                        body = message[8:]  # Remove header
                        try:
                            data = json.loads(body)
                            event_type = data.get("type")
                            event_data = data.get("data", {})
                            
                            if on_status:
                                on_status(event_type, event_data)
                        except json.JSONDecodeError:
                            pass
                    
                    elif message.startswith("|MSG|01|"):
                        # Error notification
                        body = message[8:]  # Remove header
                        try:
                            data = json.loads(body)
                            error_code = data.get("code")
                            error_message = data.get("message")
                            
                            if on_error:
                                on_error(error_code, error_message)
                        except json.JSONDecodeError:
                            pass
                    
                    elif message.startswith("|MSG|02|"):
                        # Heartbeat - no action needed
                        pass
                        
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def stop_live(self) -> None:
        """Stop live streaming."""
        if not self.websocket:
            logger.info("No WebSocket connection to stop live streaming")
            self.live_id = None
            return
        
        if not self.live_id:
            logger.info("No live_id to stop, already stopped")
            return
        
        try:
            logger.info(f"Stopping live streaming for live_id: {self.live_id}")
            message = "|CTL|01|"
            await self.websocket.send(message)
            logger.info(f"Stop command sent for live_id: {self.live_id}")
            self.live_id = None
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Connection closed while stopping live: {e}")
            # Don't raise error, just log it and clean up
            self.live_id = None
        except Exception as e:
            logger.error(f"Error stopping live: {e}")
            # Clean up even if there's an error
            self.live_id = None
            # Don't raise error for stop_live, just log it
            logger.warning(f"Failed to stop live streaming: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket service."""
        if self.websocket:
            try:
                # Stop live streaming first if active
                if self.live_id:
                    await self.stop_live()
                    # Wait a bit for the stop command to be processed
                    await asyncio.sleep(0.5)
                
                # Close WebSocket connection properly
                if self.websocket and self.websocket.state != websockets.protocol.State.CLOSED:
                    await asyncio.wait_for(
                        self.websocket.close(code=1000, reason="Normal closure"),
                        timeout=10.0
                    )
                    
            except asyncio.TimeoutError:
                logger.warning("WebSocket close timeout, forcing disconnection")
            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket already closed")
            except Exception as e:
                logger.error(f"Error during WebSocket disconnect: {e}")
            finally:
                self.websocket = None
                self.live_id = None
                logger.info("Digital Human WebSocket disconnected")
    
    def is_connected(self) -> bool:
        """Check if WebSocket connection is active."""
        return (self.websocket is not None and 
                self.websocket.state == websockets.protocol.State.OPEN)
    
    async def health_check(self) -> bool:
        """Perform a health check on the connection."""
        if not self.is_connected():
            return False
        
        try:
            # Send a ping to check if connection is responsive
            pong_waiter = await self.websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=5.0)
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    @staticmethod
    def create_rtmp_config(rtmp_addr: str) -> Dict[str, Any]:
        """
        Create RTMP streaming configuration.
        
        Args:
            rtmp_addr: RTMP streaming address
            
        Returns:
            RTMP configuration dict
        """
        return {
            "type": StreamingType.RTMP.value,
            "rtmp_addr": rtmp_addr
        }
    
    @staticmethod
    def create_rtc_config(app_id: str, room_id: str, uid: str, token: str) -> Dict[str, Any]:
        """
        Create ByteRTC streaming configuration.
        
        Args:
            app_id: ByteRTC application ID
            room_id: ByteRTC room ID
            uid: ByteRTC user ID
            token: ByteRTC temporary token
            
        Returns:
            ByteRTC configuration dict
        """
        return {
            "type": StreamingType.BYTERTC.value,
            "rtc_app_id": app_id,
            "rtc_room_id": room_id,
            "rtc_uid": uid,
            "rtc_token": token
        }
    
    @staticmethod
    def create_video_config(width: int = 1280, 
                           height: int = 720, 
                           bitrate: int = 2000) -> Dict[str, Any]:
        """
        Create video configuration.
        
        Args:
            width: Video width (240-1920)
            height: Video height (240-1920)
            bitrate: Video bitrate in kbps (100-8000)
            
        Returns:
            Video configuration dict
        """
        return {
            "video_width": max(240, min(1920, width)),
            "video_height": max(240, min(1920, height)),
            "bitrate": max(100, min(8000, bitrate))
        }
    
    @staticmethod
    def create_role_config(role_width: Optional[int] = None,
                          left_offset: Optional[int] = None,
                          top_offset: Optional[int] = None) -> Dict[str, Any]:
        """
        Create role configuration.
        
        Args:
            role_width: Avatar width (100 <= value <= 5760)
            left_offset: Left offset for avatar positioning
            top_offset: Top offset for avatar positioning
            
        Returns:
            Role configuration dict
        """
        config = {}
        
        if role_width is not None:
            config["role_width"] = max(100, min(5760, role_width))
        
        if left_offset is not None:
            config["role_left_offset"] = left_offset
        
        if top_offset is not None:
            config["role_top_offset"] = max(0, top_offset)
        
        return config