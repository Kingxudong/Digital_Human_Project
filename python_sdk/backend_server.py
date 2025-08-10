"""Backend server for integrated HiAgent LLM, TTS, and Digital Human functionality."""

import asyncio
import json
import uuid
import websockets
from typing import Dict, Any, Optional, Set
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
import uvicorn
from loguru import logger

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import HiAgentConfig, TTSConfig, DigitalHumanConfig, STTConfig
from llm_client import LLMClient
from tts_client import TTSClient
from digital_human_client import DigitalHumanClient, AvatarType
from stt_client import STTClient


from sauc_websocket_demo import MicrophoneRecorder, AsrWsClient


app = FastAPI(title="HiAgent Integrated Backend", version="1.0.0")


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with user-friendly messages."""

    """
    处理HTTP异常，返回用户友好的错误信息
    
    功能：
    - 捕获所有HTTP异常（如404、500等）
    - 统一错误响应格式
    - 提供中文错误提示
    - 记录错误日志
    
    参数：
    - request: FastAPI请求对象
    - exc: HTTP异常对象
    
    返回：
    - JSONResponse: 标准化的错误响应
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail, "message": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with user-friendly messages."""

    """
    处理请求参数验证错误
    
    功能：
    - 捕获Pydantic验证错误
    - 提供参数错误提示
    - 帮助用户理解输入要求
    
    常见错误：
    - 缺少必需参数
    - 参数类型错误
    - 参数格式错误
    """
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "请求参数错误",
            "message": "请检查输入参数是否正确",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with user-friendly messages."""

    """
    处理一般异常，记录日志并返回友好提示
    
    功能：
    - 捕获所有未处理的异常
    - 记录详细错误日志
    - 隐藏敏感错误信息
    - 提供通用错误提示
    
    安全考虑：
    - 不暴露内部错误详情
    - 记录完整错误堆栈
    - 防止信息泄露
    """

    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "服务器内部错误",
            "message": "系统暂时不可用，请稍后重试",
        },
    )


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源，生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # 允许的HTTP方法
    allow_headers=["*"],  # 允许所有请求头
    expose_headers=["Content-Type", "Content-Length", "Cache-Control"],  # 暴露的响应头
    max_age=3600,  # 预检请求缓存时间
)

# Global clients
llm_client: LLMClient | None = None
tts_client: TTSClient | None = None
digital_human_client: DigitalHumanClient | None = None
stt_client: STTClient | None = None
# llm_client: Optional[LLMClient] = None
# tts_client: Optional[TTSClient] = None
# digital_human_client: Optional[DigitalHumanClient] = None
# Active sessions

# Active sessions
active_sessions: Dict[str, Dict[str, Any]] = {}

# Track active streaming sessions and cancel flags
# session_id -> { "live_id": str | None, "cancel_event": asyncio.Event }
active_streams: Dict[str, Dict[str, Any]] = {}

# live_id -> set(session_id)
live_to_sessions: Dict[str, Set[str]] = {}


def register_stream_session(session_id: str, live_id: Optional[str]) -> asyncio.Event:
    """注册一个流式会话并返回用于取消的事件对象。"""
    cancel_event = asyncio.Event()
    active_streams[session_id] = {
        "live_id": live_id,
        "cancel_event": cancel_event,
    }
    if live_id:
        if live_id not in live_to_sessions:
            live_to_sessions[live_id] = set()
        live_to_sessions[live_id].add(session_id)
    return cancel_event


def cancel_stream_by_session(session_id: str) -> int:
    """通过session_id取消流式会话，返回被触发的事件数量(0或1)。"""
    try:
        stream = active_streams.get(session_id)
        if not stream:
            return 0
        cancel_event: asyncio.Event = stream.get("cancel_event")
        if cancel_event and not cancel_event.is_set():
            cancel_event.set()
        # 延后在流结束时清理active_streams，避免竞态
        return 1
    except Exception:
        return 0


def cancel_streams_by_live_id(live_id: str) -> int:
    """通过live_id取消所有相关流式会话，返回触发的事件数量。"""
    triggered = 0
    session_ids = list(live_to_sessions.get(live_id, set()))
    for sid in session_ids:
        triggered += cancel_stream_by_session(sid)
    return triggered


def cleanup_stream_session(session_id: str) -> None:
    """清理会话的注册信息。"""
    stream = active_streams.pop(session_id, None)
    if not stream:
        return
    live_id = stream.get("live_id")
    if (
        live_id
        and live_id in live_to_sessions
        and session_id in live_to_sessions[live_id]
    ):
        live_to_sessions[live_id].discard(session_id)
        if not live_to_sessions[live_id]:
            del live_to_sessions[live_id]


# Connection lock to prevent concurrent connection attempts
connection_lock = asyncio.Lock()

# Request tracking to prevent duplicate requests
pending_requests: Dict[str, asyncio.Task] = {}

# Failed request tracking with cooldown period
failed_requests: Dict[str, float] = {}  # live_id -> timestamp
COOLDOWN_PERIOD = 10.0  # 10 seconds cooldown after failure


class JoinRoomRequest(BaseModel):
    """Request model for digital human joining RTC room."""

    live_id: str
    avatar_type: str = "3min"  # "pic" or "3min"
    role: Optional[str] = None
    rtc_app_id: Optional[str] = None
    rtc_room_id: Optional[str] = None
    rtc_uid: Optional[str] = None
    rtc_token: Optional[str] = None
    background: Optional[str] = None
    video_config: Optional[Dict[str, Any]] = None
    role_config: Optional[Dict[str, Any]] = None


class QueryRequest(BaseModel):
    """Request model for query processing."""

    query: str
    user_id: str
    session_id: Optional[str] = None
    speaker: str = "BV001_streaming"
    live_id: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    """Initialize clients on startup."""

    """
    应用启动时初始化所有客户端
    
    执行顺序：
    1. 初始化LLM客户端
    2. 初始化TTS客户端  
    3. 初始化数字人客户端
    4. 初始化STT客户端
    5. 启动清理任务
    
    错误处理：
    - 每个客户端初始化失败都会记录日志
    - 不会因为单个客户端失败而阻止启动
    - 提供详细的初始化状态反馈
    """

    global llm_client, tts_client, digital_human_client, stt_client

    logger.info("Initializing clients...")

    # Initialize LLM client
    llm_client = LLMClient(
        base_url=HiAgentConfig.BASE_URL, api_key=HiAgentConfig.API_KEY
    )

    # Initialize TTS client
    tts_client = TTSClient(
        app_key=TTSConfig.APPKEY,
        access_key=TTSConfig.ACCESS_KEY,
        resource_id=TTSConfig.RESOURCE_ID,
        verify_ssl=False,
    )

    # Initialize Digital Human client
    digital_human_client = DigitalHumanClient(
        appid=DigitalHumanConfig.APPID, token=DigitalHumanConfig.TOKEN, verify_ssl=False
    )

    # Initialize STT client
    stt_client = STTClient(
        app_key=STTConfig.APP_KEY,
        access_key=STTConfig.ACCESS_KEY,
        resource_id=STTConfig.RESOURCE_ID,
        verify_ssl=STTConfig.VERIFY_SSL,
    )

    # Start cleanup task for pending requests
    asyncio.create_task(cleanup_pending_requests())

    logger.info("All clients initialized successfully")


async def cleanup_pending_requests():
    """Periodically clean up completed or failed pending requests."""

    """
    定期清理已完成或失败的待处理请求
    
    清理策略：
    - 每30秒执行一次清理
    - 清理已完成的任务
    - 清理过期的失败请求（10秒冷却期）
    
    内存管理：
    - 防止内存泄漏
    - 保持请求队列清洁
    - 优化系统性能
    """

    global pending_requests, failed_requests

    while True:
        try:
            # Clean up completed tasks
            completed_live_ids = []
            for live_id, task in pending_requests.items():
                if task.done():
                    completed_live_ids.append(live_id)

            for live_id in completed_live_ids:
                del pending_requests[live_id]
                logger.debug(f"Cleaned up completed request for {live_id}")

            # Clean up expired failed requests
            current_time = asyncio.get_event_loop().time()
            expired_failed_requests = []
            for live_id, failure_time in failed_requests.items():
                if current_time - failure_time > COOLDOWN_PERIOD:
                    expired_failed_requests.append(live_id)

            for live_id in expired_failed_requests:
                del failed_requests[live_id]
                logger.debug(f"Cleaned up expired failed request for {live_id}")

            # Sleep for 30 seconds before next cleanup
            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Error in cleanup_pending_requests: {e}")
            await asyncio.sleep(30)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""

    """
    应用关闭时清理资源
    
    清理步骤：
    1. 断开TTS WebSocket连接
    2. 断开数字人WebSocket连接
    3. 记录关闭日志
    
    优雅关闭：
    - 等待连接正常关闭
    - 清理所有活跃会话
    - 释放系统资源
    """

    global tts_client, digital_human_client

    logger.info("Shutting down clients...")

    if tts_client and tts_client.websocket:
        await tts_client.disconnect()

    if digital_human_client and digital_human_client.websocket:
        await digital_human_client.disconnect()

    logger.info("All clients shut down")


@app.post("/api/digital_human_develop/join_room")
async def join_room(request: JoinRoomRequest):
    """Make digital human join RTC room."""

    """
    让数字人加入RTC房间
    
    完整流程：
    1. 验证请求参数
    2. 检查现有会话状态
    3. 防止重复请求和冷却期
    4. 建立WebSocket连接
    5. 启动数字人直播
    6. 管理会话状态
    
    错误处理：
    - 连接超时处理
    - 认证失败处理
    - 网络异常处理
    - 服务不可用处理
    
    并发控制：
    - 使用连接锁防止并发连接
    - 跟踪待处理请求
    - 实现冷却期机制
    """
    logger.info(
        f"收到join_room请求: {request.live_id}, avatar_type: {request.avatar_type}, role: {request.role}"
    )
    try:
        global digital_human_client, connection_lock, pending_requests

        if not digital_human_client:
            raise HTTPException(
                status_code=500, detail="Digital human client not initialized"
            )

        # Check if session already exists and validate its state
        if request.live_id in active_sessions:
            session = active_sessions[request.live_id]
            logger.info(f"Found existing session for {request.live_id}: {session}")

            # Check if the session is actually active and valid
            if session["status"] == "active":
                # Validate that digital human client is actually connected and working
                if (
                    digital_human_client
                    and digital_human_client.is_connected()
                    and digital_human_client.live_id == request.live_id
                ):
                    logger.info(
                        f"Session {request.live_id} is active and valid, returning existing session"
                    )
                    return {
                        "success": True,
                        "message": "数字人已在房间中",
                        "live_id": request.live_id,
                        "result": {"status": "already_active"},
                    }
                else:
                    logger.warning(
                        f"Session {request.live_id} exists but client is not properly connected. Cleaning up stale session."
                    )
                    # Clean up stale session
                    del active_sessions[request.live_id]
                    if (
                        digital_human_client
                        and digital_human_client.live_id == request.live_id
                    ):
                        digital_human_client.live_id = None
            else:
                logger.info(
                    f"Session {request.live_id} exists but status is {session['status']}, cleaning up"
                )
                del active_sessions[request.live_id]

        # Check for pending request
        if request.live_id in pending_requests:
            pending_task = pending_requests[request.live_id]
            if not pending_task.done():
                logger.warning(f"Request for {request.live_id} already in progress")
                raise HTTPException(
                    status_code=429, detail="请求正在进行中，请稍后重试"
                )

        # Check for cooldown period after failed request
        current_time = asyncio.get_event_loop().time()
        if request.live_id in failed_requests:
            time_since_failure = current_time - failed_requests[request.live_id]
            if time_since_failure < COOLDOWN_PERIOD:
                remaining_cooldown = COOLDOWN_PERIOD - time_since_failure
                logger.warning(
                    f"Request for {request.live_id} is in cooldown period. {remaining_cooldown:.1f}s remaining"
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁，请等待 {int(remaining_cooldown)} 秒后重试",
                )
            else:
                # Remove from failed requests if cooldown period has passed
                del failed_requests[request.live_id]

        # Use connection lock to prevent concurrent connection attempts
        async with connection_lock:
            # Check again for pending request after acquiring lock
            if request.live_id in pending_requests:
                pending_task = pending_requests[request.live_id]
                if not pending_task.done():
                    logger.warning(
                        f"Request for {request.live_id} already in progress (after lock)"
                    )
                    raise HTTPException(
                        status_code=429, detail="请求正在进行中，请稍后重试"
                    )

            # Quick connection check - if already connected and working, skip connection process
            if (
                digital_human_client
                and digital_human_client.is_connected()
                and digital_human_client.live_id != request.live_id
            ):
                logger.info(
                    "Digital human client already connected and working, skipping connection process"
                )
                # Continue directly to start_live_rtc

            # Create task for this request
            async def join_room_task():
                try:
                    # Stable connection logic with better error handling
                    max_retries = 3  # 增加一次容错重试（首次失败后断开重连再试一次）
                    retry_count = 0

                    while retry_count < max_retries:
                        try:
                            # Connect if not already connected
                            if not digital_human_client.websocket:
                                logger.info(
                                    f"Digital human client not connected, attempting to connect... (attempt {retry_count + 1})"
                                )
                                # Client has its own retry logic, so we use a longer timeout
                                await asyncio.wait_for(
                                    digital_human_client.connect(), timeout=45.0
                                )
                                logger.info(
                                    "Digital human client connected successfully"
                                )

                            # Check if connection is still alive
                            elif (
                                digital_human_client.websocket
                                and digital_human_client.websocket.state
                                == websockets.protocol.State.CLOSED
                            ):
                                logger.warning(
                                    f"Digital human WebSocket connection is closed, reconnecting... (attempt {retry_count + 1})"
                                )
                                await asyncio.wait_for(
                                    digital_human_client.connect(), timeout=45.0
                                )
                                logger.info(
                                    "Digital human client reconnected successfully"
                                )

                            # Check if connection is actually open and healthy
                            if not digital_human_client.is_connected():
                                raise Exception("Connection is not in OPEN state")

                            # Perform health check
                            try:
                                health_ok = await asyncio.wait_for(
                                    digital_human_client.health_check(), timeout=10.0
                                )
                                if not health_ok:
                                    raise Exception("Connection health check failed")
                            except Exception as health_error:
                                logger.warning(f"Health check failed: {health_error}")
                                raise Exception(
                                    f"Connection not healthy: {health_error}"
                                )

                            break  # Success, exit retry loop

                        except asyncio.TimeoutError:
                            retry_count += 1
                            logger.warning(
                                f"Connection attempt {retry_count} timed out"
                            )

                            if retry_count >= max_retries:
                                logger.error(
                                    f"Failed to connect after {max_retries} attempts due to timeout"
                                )
                                raise HTTPException(
                                    status_code=408, detail="连接超时，请检查网络连接"
                                )

                            # Wait before retry
                            await asyncio.sleep(3)

                        except Exception as connect_error:
                            retry_count += 1
                            logger.warning(
                                f"Connection attempt {retry_count} failed: {connect_error}"
                            )
                            # 主动断开以清理异常状态
                            try:
                                await digital_human_client.disconnect()
                            except Exception:
                                pass

                            if retry_count >= max_retries:
                                logger.error(
                                    f"Failed to connect after {max_retries} attempts"
                                )
                                raise HTTPException(
                                    status_code=503, detail="连接失败，请稍后重试"
                                )

                            # Wait before retry
                            await asyncio.sleep(3)

                    # Use provided config or defaults
                    avatar_type = (
                        AvatarType.THREE_MIN
                        if request.avatar_type == "3min"
                        else AvatarType.PIC
                    )
                    role = request.role or DigitalHumanConfig.ROLE
                    rtc_app_id = request.rtc_app_id or DigitalHumanConfig.RTC_APP_ID
                    rtc_room_id = request.rtc_room_id or DigitalHumanConfig.RTC_ROOM_ID
                    rtc_uid = request.rtc_uid or DigitalHumanConfig.RTC_UID
                    rtc_token = request.rtc_token or DigitalHumanConfig.RTC_TOKEN

                    # Start live streaming with optimized timeout
                    try:
                        result = await asyncio.wait_for(
                            digital_human_client.start_live_rtc(
                                live_id=request.live_id,
                                avatar_type=avatar_type,
                                role=role,
                                rtc_app_id=rtc_app_id,
                                rtc_room_id=rtc_room_id,
                                rtc_uid=rtc_uid,
                                rtc_token=rtc_token,
                                background=request.background,
                                video_config=request.video_config,
                                role_config=request.role_config,
                            ),
                            timeout=30.0,  # Reduced from 60 to 30 seconds
                        )
                    except asyncio.TimeoutError:
                        raise HTTPException(
                            status_code=408, detail="启动直播超时，请稍后重试"
                        )

                    # Store session info
                    active_sessions[request.live_id] = {
                        "live_id": request.live_id,
                        "avatar_type": avatar_type.value,
                        "role": role,
                        "rtc_room_id": rtc_room_id,
                        "status": "active",
                        "created_at": asyncio.get_event_loop().time(),
                    }

                    logger.info(f"Digital human joined room: {request.live_id}")

                    return {
                        "success": True,
                        "message": "Digital human successfully joined RTC room",
                        "live_id": request.live_id,
                        "result": result,
                    }

                except Exception as e:
                    logger.error(f"Failed to join room: {e}", exc_info=True)
                    raise e
                finally:
                    # Clean up pending request
                    if request.live_id in pending_requests:
                        del pending_requests[request.live_id]

            # Create and track the task
            task = asyncio.create_task(join_room_task())
            pending_requests[request.live_id] = task

            # Wait for the task to complete with timeout
            try:
                result = await asyncio.wait_for(task, timeout=90.0)  # 90秒总超时
                return result
            except asyncio.TimeoutError:
                # 如果任务超时，清理并抛出异常
                if request.live_id in pending_requests:
                    del pending_requests[request.live_id]
                raise HTTPException(status_code=408, detail="请求超时，请稍后重试")

    except HTTPException:
        # Record failed request for cooldown period
        failed_requests[request.live_id] = asyncio.get_event_loop().time()
        logger.warning(
            f"Request failed for {request.live_id}, added to cooldown period"
        )
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to join room: {e}", exc_info=True)
        # Clean up any partial state
        if request.live_id in active_sessions:
            del active_sessions[request.live_id]
        if request.live_id in pending_requests:
            del pending_requests[request.live_id]

        # Record failed request for cooldown period
        failed_requests[request.live_id] = asyncio.get_event_loop().time()
        logger.warning(
            f"Request failed for {request.live_id}, added to cooldown period"
        )

        # Provide user-friendly error messages
        error_message = "连接失败，请稍后重试"
        if "timeout" in str(e).lower():
            error_message = "连接超时，请检查网络后重试"
        elif "connection" in str(e).lower():
            error_message = "网络连接异常，请检查网络设置"
        elif "authentication" in str(e).lower() or "token" in str(e).lower():
            error_message = "认证失败，请重新登录"
        elif "service" in str(e).lower() or "unavailable" in str(e).lower():
            error_message = "服务暂时不可用，请稍后重试"

        raise HTTPException(status_code=500, detail=error_message)


@app.post("/api/query/stream")
async def process_query_stream(request: QueryRequest):
    """Process query with streaming LLM -> TTS -> Digital Human pipeline."""

    """
    处理流式AI对话：LLM → TTS → 数字人
    
    完整流程：
    1. 验证客户端初始化状态
    2. 生成会话ID
    3. 创建LLM对话
    4. 连接TTS服务
    5. 流式处理LLM响应
    6. 实时TTS语音合成
    7. 驱动数字人动画
    8. 返回流式响应
    
    技术特点：
    - 异步流式处理
    - 实时音频合成
    - 低延迟响应
    - 错误恢复机制
    """

    try:
        global llm_client, tts_client, digital_human_client

        # Log incoming request
        logger.info(f"=== Processing Query Stream Request ===")
        logger.info(f"User ID: {request.user_id}")
        logger.info(f"Query: {request.query}")
        logger.info(f"Speaker: {request.speaker}")
        logger.info(f"Live ID: {request.live_id}")
        logger.info(f"Session ID: {request.session_id}")

        if not all([llm_client, tts_client, digital_human_client]):
            logger.error("Clients not initialized")
            raise HTTPException(status_code=500, detail="Clients not initialized")

        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())
        # Register cancel control for this streaming session
        cancel_event = register_stream_session(session_id, request.live_id)
        logger.info(f"Using session ID: {session_id}")

        # Create LLM conversation if needed
        conversation_id = llm_client.create_conversation(request.user_id)
        logger.info(f"Created/Using conversation ID: {conversation_id}")

        # Connect TTS if not connected
        if not tts_client.websocket:
            logger.info("Connecting to TTS service...")
            await tts_client.connect()
            logger.info("TTS service connected successfully")

        async def stream_pipeline():
            """Stream processing pipeline: LLM -> TTS -> Digital Human."""

            """
            流处理管道：LLM → TTS → 数字人
            
            处理步骤：
            1. 发送开始信号
            2. 流式LLM响应处理
            3. 句子级别音频合成
            4. 数字人音频驱动
            5. 发送完成信号
            """

            try:
                # Buffer for accumulating text
                text_buffer = ""
                sentence_buffer = ""

                logger.info(f"Starting stream pipeline for session: {session_id}")

                # Send start signal
                start_data = {
                    "type": "start",
                    "session_id": session_id,
                    "query": request.query,
                }
                yield f"data: {json.dumps(start_data)}\n\n"
                logger.info(f"Sent start signal for query: {request.query}")

                # Early cancellation check
                if cancel_event.is_set():
                    yield f"data: {json.dumps({"type": "cancelled", "session_id": session_id})}\n\n"
                    return

                # Stream LLM responses
                logger.info(f"Starting LLM chat stream...")
                llm_response_count = 0
                for llm_response in llm_client.chat_stream(
                    user_id=request.user_id,
                    conversation_id=conversation_id,
                    query=request.query,
                ):
                    # Check cancellation between chunks
                    if cancel_event.is_set():
                        yield f"data: {json.dumps({"type": "cancelled", "session_id": session_id})}\n\n"
                        break
                    llm_response_count += 1
                    logger.debug(f"LLM response #{llm_response_count}: {llm_response}")
                    # Extract text content from LLM response
                    if "answer" in llm_response:
                        text_chunk = llm_response["answer"]
                        text_buffer += text_chunk
                        sentence_buffer += text_chunk

                        # Yield text chunk immediately for real-time display
                        text_data = {
                            "type": "text_chunk",
                            "content": text_chunk,
                            "accumulated_text": text_buffer,
                        }
                        yield f"data: {json.dumps(text_data)}\n\n"

                        # Check if we have a complete sentence
                        if any(
                            punct in sentence_buffer
                            for punct in ["。", "！", "？", ".", "!", "?"]
                        ):
                            logger.info(
                                f"Complete sentence detected: {sentence_buffer.strip()}"
                            )
                            # Send sentence completion signal
                            sentence_data = {
                                "type": "sentence_complete",
                                "sentence": sentence_buffer.strip(),
                                "status": "processing_audio",
                            }
                            yield f"data: {json.dumps(sentence_data)}\n\n"

                            # Send sentence to TTS and get audio
                            try:
                                request.speaker = (
                                    "multi_female_shuangkuaisisi_moon_bigtts"
                                )
                                logger.info(
                                    f"Starting TTS synthesis for: {sentence_buffer.strip()}, speaker: {request.speaker}"
                                )

                                # 检查TTS连接状态，如果断开则重新连接
                                websocket_closed = False
                                try:
                                    if not tts_client.websocket:
                                        websocket_closed = True
                                    else:
                                        # 尝试检查WebSocket状态
                                        if hasattr(tts_client.websocket, "closed"):
                                            websocket_closed = (
                                                tts_client.websocket.closed
                                            )
                                        elif hasattr(tts_client.websocket, "state"):
                                            websocket_closed = (
                                                tts_client.websocket.state.name
                                                in ["CLOSED", "CLOSING"]
                                            )
                                        else:
                                            websocket_closed = False
                                except Exception:
                                    websocket_closed = True

                                if websocket_closed:
                                    logger.warning(
                                        "TTS WebSocket连接已断开，尝试重新连接..."
                                    )
                                    try:
                                        await tts_client.connect()
                                        logger.info("TTS WebSocket重新连接成功")
                                    except Exception as reconnect_error:
                                        logger.error(
                                            f"TTS重新连接失败: {reconnect_error}"
                                        )
                                        raise Exception(
                                            f"TTS连接失败: {reconnect_error}"
                                        )

                                # 使用安全的TTS合成函数
                                # 在TTS过程中也支持取消
                                sentence_audio_chunks = await safe_tts_synthesize(
                                    text=sentence_buffer.strip(),
                                    speaker=request.speaker,
                                    session_id=session_id,
                                    cancel_event=cancel_event,
                                )

                                # 处理音频片段
                                for audio_chunk_count, audio_chunk in enumerate(
                                    sentence_audio_chunks, 1
                                ):
                                    if cancel_event.is_set():
                                        yield f"data: {json.dumps({"type": "cancelled", "session_id": session_id})}\n\n"
                                        break
                                    logger.debug(
                                        f"Processing audio chunk #{audio_chunk_count}, size: {len(audio_chunk)} bytes"
                                    )

                                    # # 调试：保存原始TTS音频块
                                    # debug_filename = f"debug_tts_chunk_{session_id}_{audio_chunk_count}.pcm"
                                    # try:
                                    #     with open(debug_filename, "wb") as f:
                                    #         f.write(audio_chunk)
                                    #     logger.info(f"Saved TTS audio chunk to {debug_filename}")
                                    # except Exception as save_error:
                                    #     logger.error(f"Failed to save TTS audio chunk: {save_error}")

                                    # Convert audio to digital human format and drive avatar
                                    if (
                                        digital_human_client.websocket
                                        and request.live_id
                                    ):
                                        logger.debug(
                                            f"Driving digital human with audio chunk (size: {len(audio_chunk)})"
                                        )

                                        # # 调试：保存发送到数字人的音频数据
                                        # dh_debug_filename = f"debug_dh_audio_{session_id}_{audio_chunk_count}.bin"
                                        # try:
                                        #     with open(dh_debug_filename, "wb") as f:
                                        #         f.write(audio_chunk)
                                        #     logger.info(f"Saved digital human audio data to {dh_debug_filename}")
                                        # except Exception as save_error:
                                        #     logger.error(f"Failed to save digital human audio: {save_error}")

                                        await digital_human_client.drive_with_streaming_audio(
                                            audio_chunk
                                        )
                                        logger.debug(
                                            "Digital human driven successfully"
                                        )
                                    else:
                                        logger.warning(
                                            f"Digital human not available - websocket: {bool(digital_human_client.websocket)}, live_id: {request.live_id}"
                                        )

                                    # Yield audio progress info
                                    audio_data = {
                                        "type": "audio_chunk",
                                        "sentence": sentence_buffer.strip(),
                                        "audio_size": len(audio_chunk),
                                        "status": "driving_avatar",
                                    }
                                    yield f"data: {json.dumps(audio_data)}\n\n"

                                # # 调试：保存整个句子的完整音频
                                # if sentence_audio_chunks:
                                #     complete_audio = b''.join(sentence_audio_chunks)
                                #     complete_filename = f"debug_complete_sentence_{session_id}_{len(sentence_audio_chunks)}_chunks.pcm"
                                #     try:
                                #         with open(complete_filename, "wb") as f:
                                #             f.write(complete_audio)
                                #         logger.info(f"Saved complete sentence audio to {complete_filename} (total size: {len(complete_audio)} bytes)")
                                #     except Exception as save_error:
                                #         logger.error(f"Failed to save complete sentence audio: {save_error}")

                                # Send sentence processing complete signal
                                logger.info(
                                    f"TTS synthesis completed for sentence: {sentence_buffer.strip()}"
                                )
                                sentence_complete_data = {
                                    "type": "sentence_processed",
                                    "sentence": sentence_buffer.strip(),
                                    "status": "complete",
                                }
                                yield f"data: {json.dumps(sentence_complete_data)}\n\n"

                            except Exception as tts_error:
                                logger.error(
                                    f"TTS error for sentence '{sentence_buffer.strip()}': {tts_error}"
                                )
                                logger.error(
                                    f"TTS error details: {type(tts_error).__name__}: {str(tts_error)}"
                                )
                                tts_error_data = {
                                    "type": "tts_error",
                                    "sentence": sentence_buffer.strip(),
                                    "error": str(tts_error),
                                }
                                yield f"data: {json.dumps(tts_error_data)}\n\n"

                            sentence_buffer = ""

                # Process any remaining text
                if sentence_buffer.strip() and not cancel_event.is_set():
                    # Send final sentence signal
                    final_sentence_data = {
                        "type": "final_sentence",
                        "sentence": sentence_buffer.strip(),
                        "status": "processing_audio",
                    }
                    yield f"data: {json.dumps(final_sentence_data)}\n\n"

                    try:
                        # 检查TTS连接状态，如果断开则重新连接
                        websocket_closed = False
                        try:
                            if not tts_client.websocket:
                                websocket_closed = True
                            else:
                                # 尝试检查WebSocket状态
                                if hasattr(tts_client.websocket, "closed"):
                                    websocket_closed = tts_client.websocket.closed
                                elif hasattr(tts_client.websocket, "state"):
                                    websocket_closed = (
                                        tts_client.websocket.state.name
                                        in ["CLOSED", "CLOSING"]
                                    )
                                else:
                                    websocket_closed = False
                        except Exception:
                            websocket_closed = True

                        if websocket_closed:
                            logger.warning("TTS WebSocket连接已断开，尝试重新连接...")
                            try:
                                await tts_client.connect()
                                logger.info("TTS WebSocket重新连接成功")
                            except Exception as reconnect_error:
                                logger.error(f"TTS重新连接失败: {reconnect_error}")
                                raise Exception(f"TTS连接失败: {reconnect_error}")

                        # 使用安全的TTS合成函数
                        final_audio_chunks = await safe_tts_synthesize(
                            text=sentence_buffer.strip(),
                            speaker=request.speaker,
                            session_id=session_id,
                            cancel_event=cancel_event,
                        )

                        # 处理最终音频片段
                        for audio_chunk in final_audio_chunks:
                            if digital_human_client.websocket and request.live_id:
                                await digital_human_client.drive_with_streaming_audio(
                                    audio_chunk
                                )

                            audio_data = {
                                "type": "final_audio_chunk",
                                "sentence": sentence_buffer.strip(),
                                "audio_size": len(audio_chunk),
                                "status": "driving_avatar",
                            }
                            yield f"data: {json.dumps(audio_data)}\n\n"
                    except Exception as final_tts_error:
                        logger.error(f"Final TTS error: {final_tts_error}")
                        final_error_data = {
                            "type": "final_tts_error",
                            "sentence": sentence_buffer.strip(),
                            "error": str(final_tts_error),
                        }
                        yield f"data: {json.dumps(final_error_data)}\n\n"

                # Finish streaming audio to digital human
                if (
                    digital_human_client.websocket
                    and request.live_id
                    and not cancel_event.is_set()
                ):
                    try:
                        await digital_human_client.finish_streaming_audio()
                        logger.info("Digital human streaming audio finished")
                    except Exception as finish_error:
                        logger.error(
                            f"Failed to finish digital human streaming audio: {finish_error}"
                        )
                        # Don't let this error stop the pipeline completion

                # Send completion signal with full text
                logger.info(f"=== Stream Pipeline Completed ===")
                logger.info(f"Session ID: {session_id}")
                logger.info(f"Full generated text: {text_buffer}")
                logger.info(f"Total LLM responses: {llm_response_count}")

                complete_data = {
                    "type": "complete",
                    "full_text": text_buffer,
                    "session_id": session_id,
                    "status": "finished",
                }
                yield f"data: {json.dumps(complete_data)}\n\n"

            except asyncio.CancelledError:
                logger.info(f"Stream pipeline cancelled: {session_id}")
                try:
                    yield f"data: {json.dumps({"type": "cancelled", "session_id": session_id})}\n\n"
                except Exception:
                    pass
                return
            except Exception as e:
                logger.error(f"=== Error in Stream Pipeline ===")
                logger.error(f"Session ID: {session_id}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                logger.error(f"Error details: {e}", exc_info=True)
                error_data = {
                    "type": "error",
                    "message": str(e),
                    "session_id": session_id,
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            finally:
                # cleanup stream registration
                cleanup_stream_session(session_id)

        return StreamingResponse(
            stream_pipeline(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )

    except Exception as e:
        logger.error(f"=== Failed to Process Query Stream ===")
        logger.error(
            f"Request details: user_id={request.user_id}, query='{request.query}', speaker={request.speaker}, live_id={request.live_id}"
        )
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Full error details: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to process query: {str(e)}"
        )


@app.delete("/api/digital_human_develop/leave_room/{live_id}")
async def leave_room(live_id: str):
    """Make digital human leave RTC room."""
    try:
        global digital_human_client, active_sessions, pending_requests, tts_client, stt_client

        logger.info(f"Attempting to leave room: {live_id}")

        # 先取消与该live_id相关的所有流式会话
        cancelled = cancel_streams_by_live_id(live_id)
        logger.info(f"Triggered {cancelled} stream cancellations for live_id={live_id}")

        # Clean up pending requests for this live_id
        if live_id in pending_requests:
            pending_task = pending_requests[live_id]
            if not pending_task.done():
                logger.info(f"Cancelling pending request for {live_id}")
                pending_task.cancel()
            del pending_requests[live_id]

        if live_id in active_sessions:
            session = active_sessions[live_id]
            logger.info(f"Found active session for {live_id}: {session}")

            # Stop live streaming if digital human client is available
            if digital_human_client:
                try:
                    # Check if the client is connected and the live_id matches
                    if (
                        digital_human_client.websocket
                        and digital_human_client.is_connected()
                        and digital_human_client.live_id == live_id
                    ):
                        logger.info(f"Stopping live streaming for {live_id}")
                        await digital_human_client.stop_live()
                    else:
                        logger.info(
                            f"Digital human client not connected or live_id mismatch. Client live_id: {digital_human_client.live_id}"
                        )
                except Exception as stop_error:
                    logger.warning(f"Error stopping live for {live_id}: {stop_error}")
                    # Continue with cleanup even if stop fails

                # Always reset the live_id to ensure clean state
                if digital_human_client.live_id == live_id:
                    digital_human_client.live_id = None
                    logger.info(f"Reset digital human client live_id for {live_id}")

                # Force disconnect if in bad state to ensure clean reconnection
                try:
                    if (
                        digital_human_client.websocket
                        and digital_human_client.websocket.state
                        != websockets.protocol.State.CLOSED
                    ):
                        logger.info(
                            f"Force disconnecting digital human client for {live_id}"
                        )
                        await digital_human_client.disconnect()
                except Exception as disconnect_error:
                    logger.warning(
                        f"Error force disconnecting digital human client: {disconnect_error}"
                    )

            # Remove from active sessions
            del active_sessions[live_id]
            logger.info(f"Removed {live_id} from active sessions")

            # 断开TTS/STT连接（如果存在）
            try:
                if tts_client and tts_client.websocket:
                    await tts_client.disconnect()
                    logger.info("TTS client disconnected due to leave_room")
            except Exception as e:
                logger.warning(f"Error disconnecting TTS on leave_room: {e}")

            try:
                if stt_client and stt_client.is_connected:
                    await stt_client.stop_recognition()
                    await stt_client.disconnect()
                    logger.info("STT client disconnected due to leave_room")
            except Exception as e:
                logger.warning(f"Error disconnecting STT on leave_room: {e}")

            return {
                "success": True,
                "message": f"Digital human left room {live_id}",
                "cleaned_up": True,
            }
        else:
            logger.info(f"Session {live_id} not found in active sessions")
            # Even if session not found, return success to avoid frontend errors
            return {
                "success": True,
                "message": f"Session {live_id} was not active",
                "cleaned_up": False,
            }

    except Exception as e:
        logger.error(f"Failed to leave room {live_id}: {e}", exc_info=True)
        # Try to clean up anyway
        try:
            if live_id in active_sessions:
                del active_sessions[live_id]
            if live_id in pending_requests:
                del pending_requests[live_id]
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")

        # Provide user-friendly error message
        error_message = "退出房间失败，请稍后重试"
        if "timeout" in str(e).lower():
            error_message = "退出超时，请稍后重试"
        elif "connection" in str(e).lower():
            error_message = "网络连接异常，请检查网络设置"

        raise HTTPException(status_code=500, detail=error_message)


@app.post("/api/reset_connections")
async def reset_connections():
    """Reset all client connections."""

    """
    重置所有客户端连接
    
    重置步骤：
    1. 取消所有待处理请求
    2. 断开数字人客户端连接
    3. 断开TTS客户端连接
    4. 清理活跃会话
    
    使用场景：
    - 系统维护
    - 连接异常恢复
    - 内存清理
    """

    try:
        global digital_human_client, tts_client, active_sessions, pending_requests, stt_client

        logger.info("Resetting all client connections...")

        # Cancel all pending requests
        for live_id, task in pending_requests.items():
            if not task.done():
                logger.info(f"Cancelling pending request for {live_id}")
                task.cancel()
        pending_requests.clear()
        logger.info("All pending requests cancelled")

        # Cancel all streaming sessions
        for session_id in list(active_streams.keys()):
            cancel_stream_by_session(session_id)
        logger.info("All active streams cancelled")

        # Reset digital human client
        if digital_human_client:
            try:
                await digital_human_client.disconnect()
                logger.info("Digital human client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting digital human client: {e}")

        # Reset TTS client
        if tts_client and tts_client.websocket:
            try:
                await tts_client.disconnect()
                logger.info("TTS client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting TTS client: {e}")

        # Reset STT client
        if stt_client and getattr(stt_client, "is_connected", False):
            try:
                await stt_client.stop_recognition()
                await stt_client.disconnect()
                logger.info("STT client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting STT client: {e}")

        # Clear active sessions
        active_sessions.clear()
        logger.info("Active sessions cleared")

        # Clear stream registries
        active_streams.clear()
        live_to_sessions.clear()
        logger.info("Stream registries cleared")

        return {
            "success": True,
            "message": "All connections reset successfully",
            "cleaned_sessions": len(active_sessions),
            "cancelled_requests": len(pending_requests),
        }

    except Exception as e:
        logger.error(f"Failed to reset connections: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reset connections: {str(e)}"
        )


@app.get("/api/connection_status")
async def get_connection_status():
    """Get detailed connection status for debugging."""

    """
    获取详细的连接状态信息
    
    检查项目：
    - 各客户端初始化状态
    - WebSocket连接状态
    - 健康检查结果
    - 活跃会话信息
    
    返回信息：
    - 数字人客户端状态
    - TTS客户端状态
    - 连接健康状态
    - 错误信息
    """

    try:
        status = {
            "digital_human_develop": {
                "initialized": digital_human_client is not None,
                "connected": False,
                "websocket_state": "None",
                "live_id": None,
                "health_check": False,
            },
            "tts": {
                "initialized": tts_client is not None,
                "connected": False,
                "websocket_state": "None",
            },
        }

        # Check digital human client status
        if digital_human_client:
            status["digital_human_develop"][
                "connected"
            ] = digital_human_client.is_connected()
            status["digital_human_develop"]["live_id"] = digital_human_client.live_id
            if digital_human_client.websocket:
                status["digital_human_develop"][
                    "websocket_state"
                ] = digital_human_client.websocket.state.name
                # Perform health check
                try:
                    status["digital_human_develop"]["health_check"] = (
                        await asyncio.wait_for(
                            digital_human_client.health_check(), timeout=5.0
                        )
                    )
                except Exception as e:
                    status["digital_human_develop"]["health_check"] = False
                    status["digital_human_develop"]["health_check_error"] = str(e)

        # Check TTS client status
        if tts_client:
            status["tts"]["connected"] = tts_client.websocket is not None
            if tts_client.websocket:
                status["tts"]["websocket_state"] = tts_client.websocket.state.name

        return status

    except Exception as e:
        logger.error(f"Error getting connection status: {e}")
        return {"error": str(e)}


# 全局变量存储录音状态
voice_recording_sessions = {}


# TTS连接监控和重连辅助函数
async def ensure_tts_connection():
    """确保TTS连接可用，如果断开则重新连接"""
    global tts_client

    if not tts_client:
        raise Exception("TTS客户端未初始化")

    # 检查连接状态 - 使用正确的方法检查WebSocket状态
    websocket_closed = False
    try:
        if not tts_client.websocket:
            websocket_closed = True
        else:
            # 尝试检查WebSocket状态，不同版本的websockets库可能有不同的属性
            if hasattr(tts_client.websocket, "closed"):
                websocket_closed = tts_client.websocket.closed
            elif hasattr(tts_client.websocket, "state"):
                websocket_closed = tts_client.websocket.state.name in [
                    "CLOSED",
                    "CLOSING",
                ]
            else:
                # 如果无法确定状态，假设连接正常
                websocket_closed = False
    except Exception:
        websocket_closed = True

    if websocket_closed:
        logger.warning("TTS WebSocket连接已断开，尝试重新连接...")
        try:
            await tts_client.connect()
            logger.info("TTS WebSocket重新连接成功")
            return True
        except Exception as e:
            logger.error(f"TTS重新连接失败: {e}")
            raise Exception(f"TTS连接失败: {e}")

    return True


async def safe_tts_synthesize(
    text: str,
    speaker: str,
    session_id: str,
    cancel_event: Optional[asyncio.Event] = None,
):
    """安全的TTS合成，包含连接检查和重试机制和取消支持"""
    global tts_client

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Check cancellation before work
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()
            # 确保连接可用
            await ensure_tts_connection()
            # 给重连后的服务端一个极短的稳定时间，避免收到文本却来不及产出音频
            await asyncio.sleep(1.5)

            # 执行TTS合成
            audio_chunks = []
            try:
                async for audio_chunk in tts_client.synthesize_text(
                    text=text, speaker=speaker, session_id=session_id
                ):
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError()
                    audio_chunks.append(audio_chunk)
                # 若没有任何音频片段，视为失败以触发重试
                if len(audio_chunks) == 0:
                    raise Exception("TTS produced zero audio chunks after synthesis")
                logger.info(f"TTS合成成功，生成了 {len(audio_chunks)} 个音频片段")
                return audio_chunks

            except Exception as synthesis_error:
                logger.error(f"TTS合成过程中出现错误: {synthesis_error}")
                # 如果是连接相关错误，尝试重新连接
                if "ConnectionClosed" in str(synthesis_error) or "1000" in str(
                    synthesis_error
                ):
                    logger.warning("检测到WebSocket连接错误，将尝试重新连接")
                    # 强制重新连接
                    try:
                        if tts_client.websocket:
                            await tts_client.websocket.close()
                    except:
                        pass
                    tts_client.websocket = None
                    raise synthesis_error
                else:
                    raise synthesis_error

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                logger.info("TTS合成被取消")
                raise
            retry_count += 1
            logger.error(f"TTS合成失败 (尝试 {retry_count}/{max_retries}): {e}")

            if retry_count >= max_retries:
                logger.error(f"TTS合成最终失败，已达到最大重试次数")
                raise Exception(f"TTS合成失败: {e}")

            # 等待一段时间后重试
            await asyncio.sleep(2)  # 增加重试间隔

    return []


@app.post("/api/voice/single_button_control")
async def single_button_voice_control(request: Request):
    """单按钮语音控制：点击开始录音，再点击结束录音并自动输入到对话栏"""
    global voice_recording_sessions, llm_client, tts_client, digital_human_client

    try:
        # 解析请求体
        try:
            body = await request.json()
            logger.info(f"收到单按钮语音控制请求: {body}")
        except:
            body = {}

        # 获取参数
        session_id = body.get("session_id") or str(uuid.uuid4())
        user_id = body.get("user_id", "voice_user")
        action = body.get("action", "toggle")  # "toggle" 表示切换录音状态
        live_id = body.get("live_id")
        speaker = body.get("speaker", "BV001_streaming")

        logger.info(f"单按钮语音控制: session_id={session_id}, action={action}")

        # 检查当前录音状态
        is_recording = session_id in voice_recording_sessions

        if not is_recording:
            # 开始录音
            logger.info(f"开始录音，会话ID: {session_id}")

            try:
                # 创建录音器和ASR客户端

                recorder = MicrophoneRecorder()
                asr_client = AsrWsClient(
                    url="wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel"
                )

                voice_recording_sessions[session_id] = {
                    "recorder": recorder,
                    "asr_client": asr_client,
                    "user_id": user_id,
                    "start_time": asyncio.get_event_loop().time(),
                    "live_id": live_id,
                    "speaker": speaker,
                }

                # 开始录音
                recorder.start_recording()

                return {
                    "success": True,
                    "message": "开始录音",
                    "session_id": session_id,
                    "status": "recording",
                    "action": "started",
                }

            except Exception as e:
                logger.error(f"开始录音失败: {e}")
                return {
                    "success": False,
                    "message": f"开始录音失败: {str(e)}",
                    "session_id": session_id,
                    "status": "error",
                }

        else:
            # 停止录音并处理
            logger.info(f"停止录音并处理，会话ID: {session_id}")

            try:
                # 获取录音会话数据
                session_data = voice_recording_sessions[session_id]
                recorder = session_data["recorder"]
                asr_client = session_data["asr_client"]
                live_id = session_data.get("live_id")
                speaker = session_data.get("speaker", "BV001_streaming")

                # 停止录音
                recorder.stop_recording()

                # 获取音频数据
                audio_data = recorder.get_audio_data()
                logger.info(f"录音完成，音频大小: {len(audio_data)} 字节")

                # 检查音频数据是否有效
                if len(audio_data) < 1000:
                    logger.warning(f"录音数据太短: {len(audio_data)} 字节")
                    # 清理录音会话
                    del voice_recording_sessions[session_id]
                    return {
                        "success": False,
                        "message": "录音时间太短，请说话时间更长一些",
                        "session_id": session_id,
                        "status": "too_short",
                    }

                # 使用sauc_websocket_demo中的ASR功能进行语音识别
                logger.info("开始使用ASR进行语音识别...")
                try:
                    # 创建ASR客户端并执行识别
                    async with asr_client:
                        # 建立WebSocket连接
                        await asr_client.create_connection()

                        # 发送认证请求
                        await asr_client.send_full_client_request()

                        # 处理音频数据
                        recognition_text = ""
                        async for response in asr_client.start_audio_stream(
                            segment_size=asr_client.get_segment_size(audio_data),
                            content=audio_data,
                        ):
                            if response.is_final_result():
                                recognition_text = response.get_text()
                                break

                        if recognition_text:
                            logger.info(f"ASR识别成功: {recognition_text}")
                            recognition_result = {
                                "success": True,
                                "final_text": recognition_text,
                                "intermediate_text": recognition_text,
                            }
                        else:
                            logger.warning("ASR未识别到有效文本")
                            recognition_result = {
                                "success": False,
                                "message": "未能识别到有效语音",
                                "final_text": "",
                            }

                except Exception as asr_error:
                    logger.error(f"ASR识别失败: {asr_error}")
                    recognition_result = {
                        "success": False,
                        "message": f"ASR识别失败: {str(asr_error)}",
                        "final_text": "",
                    }

                if not recognition_result["success"]:
                    # 清理录音会话
                    del voice_recording_sessions[session_id]
                    return recognition_result

                recognized_text = recognition_result["final_text"]

                if not recognized_text:
                    # 清理录音会话
                    del voice_recording_sessions[session_id]
                    return {
                        "success": False,
                        "message": "未能识别到有效语音",
                        "session_id": session_id,
                        "status": "no_speech",
                    }

                logger.info(f"语音识别完成: {recognized_text}")

                # 清理录音会话
                del voice_recording_sessions[session_id]

                # 创建QueryRequest对象，开始流式处理
                query_request = QueryRequest(
                    query=recognized_text,
                    user_id=user_id,
                    session_id=session_id,
                    speaker=speaker,
                    live_id=live_id,
                )

                # 调用现有的process_query_stream功能，返回流式响应
                return await process_query_stream(query_request)

            except Exception as e:
                logger.error(f"停止录音并处理失败: {e}")
                # 清理录音会话
                if session_id in voice_recording_sessions:
                    del voice_recording_sessions[session_id]

                return {
                    "success": False,
                    "message": f"停止录音并处理失败: {str(e)}",
                    "session_id": session_id,
                    "status": "error",
                }

    except Exception as e:
        logger.error(f"单按钮语音控制失败: {e}")
        return {
            "success": False,
            "message": f"单按钮语音控制失败: {str(e)}",
            "session_id": session_id if "session_id" in locals() else "unknown",
        }


@app.post("/api/voice/record_and_process")
async def record_and_process_voice(request: Request):
    """录制完成后一次性处理语音：录音 → 识别 → 输入到对话栏"""
    global voice_recording_sessions, llm_client, tts_client, digital_human_client

    try:
        # 解析请求体
        try:
            body = await request.json()
            logger.info(f"收到录制完成处理请求: {body}")
        except:
            body = {}

        # 获取参数
        session_id = body.get("session_id") or str(uuid.uuid4())
        user_id = body.get("user_id", "voice_user")
        live_id = body.get("live_id")
        speaker = body.get("speaker", "BV001_streaming")

        logger.info(f"录制完成处理: session_id={session_id}")

        # 检查录音会话是否存在
        if session_id not in voice_recording_sessions:
            return {
                "success": False,
                "message": "未找到录音会话",
                "session_id": session_id,
                "status": "no_session",
            }

        try:
            # 获取录音会话数据
            session_data = voice_recording_sessions[session_id]
            recorder = session_data["recorder"]
            asr_client = session_data["asr_client"]
            live_id = session_data.get("live_id")
            speaker = session_data.get("speaker", "BV001_streaming")

            # 停止录音
            recorder.stop_recording()

            # 获取音频数据
            audio_data = recorder.get_audio_data()
            logger.info(f"录音完成，音频大小: {len(audio_data)} 字节")

            # 检查音频数据是否有效
            if len(audio_data) < 1000:
                logger.warning(f"录音数据太短: {len(audio_data)} 字节")
                # 清理录音会话
                del voice_recording_sessions[session_id]
                return {
                    "success": False,
                    "message": "录音时间太短，请说话时间更长一些",
                    "session_id": session_id,
                    "status": "too_short",
                }

            # 使用ASR进行语音识别
            logger.info("开始使用ASR进行语音识别...")
            try:
                # 创建ASR客户端并执行识别
                async with asr_client:
                    # 建立WebSocket连接
                    await asr_client.create_connection()

                    # 发送认证请求
                    await asr_client.send_full_client_request()

                    # 处理音频数据
                    recognition_text = ""
                    async for response in asr_client.start_audio_stream(
                        segment_size=asr_client.get_segment_size(audio_data),
                        content=audio_data,
                    ):
                        if response.is_final_result():
                            recognition_text = response.get_text()
                            break

                    if recognition_text:
                        logger.info(f"ASR识别成功: {recognition_text}")
                        recognition_result = {
                            "success": True,
                            "final_text": recognition_text,
                            "intermediate_text": recognition_text,
                        }
                    else:
                        logger.warning("ASR未识别到有效文本")
                        recognition_result = {
                            "success": False,
                            "message": "未能识别到有效语音",
                            "final_text": "",
                        }

            except Exception as asr_error:
                logger.error(f"ASR识别失败: {asr_error}")
                recognition_result = {
                    "success": False,
                    "message": f"ASR识别失败: {str(asr_error)}",
                    "final_text": "",
                }

            if not recognition_result["success"]:
                # 清理录音会话
                del voice_recording_sessions[session_id]
                return recognition_result

            recognized_text = recognition_result["final_text"]

            if not recognized_text:
                # 清理录音会话
                del voice_recording_sessions[session_id]
                return {
                    "success": False,
                    "message": "未能识别到有效语音",
                    "session_id": session_id,
                    "status": "no_speech",
                }

            logger.info(f"语音识别完成: {recognized_text}")

            # 清理录音会话
            del voice_recording_sessions[session_id]

            # 返回识别结果，不进行后续处理
            return {
                "success": True,
                "message": "语音识别完成",
                "session_id": session_id,
                "recognized_text": recognized_text,
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"录制完成处理失败: {e}")
            # 清理录音会话
            if session_id in voice_recording_sessions:
                del voice_recording_sessions[session_id]

            return {
                "success": False,
                "message": f"录制完成处理失败: {str(e)}",
                "session_id": session_id,
                "status": "error",
            }

    except Exception as e:
        logger.error(f"录制完成处理失败: {e}")
        return {
            "success": False,
            "message": f"录制完成处理失败: {str(e)}",
            "session_id": session_id if "session_id" in locals() else "unknown",
        }


if __name__ == "__main__":
    uvicorn.run(
        "backend_server:app",
        host="0.0.0.0",
        port=9000,
        reload=True,
        log_level="info",
        access_log=True,
        use_colors=True,
        loop="asyncio",
    )
