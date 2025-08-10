import asyncio
import json
import ssl
import uuid
from typing import Dict, Any, Optional, AsyncGenerator, Union

import websockets
from loguru import logger
from exceptions import TTSConnectionError, TTSSessionError, TTSProtocolError, TTSClientError

# Protocol constants from working demo
PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

# Message Type:
FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_RESPONSE = 0b1011
FULL_SERVER_RESPONSE = 0b1001
ERROR_INFORMATION = 0b1111

# Message Type Specific Flags
MsgTypeFlagNoSeq = 0b0000
MsgTypeFlagPositiveSeq = 0b1
MsgTypeFlagLastNoSeq = 0b10
MsgTypeFlagNegativeSeq = 0b11
MsgTypeFlagWithEvent = 0b100

# Message Serialization
NO_SERIALIZATION = 0b0000
JSON = 0b0001

# Message Compression
COMPRESSION_NO = 0b0000
COMPRESSION_GZIP = 0b0001

# Events
EVENT_NONE = 0
EVENT_Start_Connection = 1
EVENT_FinishConnection = 2
EVENT_ConnectionStarted = 50
EVENT_ConnectionFailed = 51
EVENT_ConnectionFinished = 52
EVENT_StartSession = 100
EVENT_FinishSession = 102
EVENT_SessionStarted = 150
EVENT_SessionFinished = 152
EVENT_SessionFailed = 153
EVENT_TaskRequest = 200
EVENT_TTSSentenceStart = 350
EVENT_TTSSentenceEnd = 351
EVENT_TTSResponse = 352


class Header:
    def __init__(
        self,
        protocol_version=PROTOCOL_VERSION,
        header_size=DEFAULT_HEADER_SIZE,
        message_type: int = 0,
        message_type_specific_flags: int = 0,
        serial_method: int = NO_SERIALIZATION,
        compression_type: int = COMPRESSION_NO,
        reserved_data=0,
    ):
        self.header_size = header_size
        self.protocol_version = protocol_version
        self.message_type = message_type
        self.message_type_specific_flags = message_type_specific_flags
        self.serial_method = serial_method
        self.compression_type = compression_type
        self.reserved_data = reserved_data

    def as_bytes(self) -> bytes:
        return bytes(
            [
                (self.protocol_version << 4) | self.header_size,
                (self.message_type << 4) | self.message_type_specific_flags,
                (self.serial_method << 4) | self.compression_type,
                self.reserved_data,
            ]
        )


class Optional:
    def __init__(
        self, event: int = EVENT_NONE, sessionId: str = None, sequence: int = None
    ):
        self.event = event
        self.sessionId = sessionId
        self.errorCode: int = 0
        self.connectionId: Union[str, None] = None
        self.response_meta_json: Union[str, None] = None
        self.sequence = sequence

    def as_bytes(self) -> bytes:
        option_bytes = bytearray()
        if self.event != EVENT_NONE:
            option_bytes.extend(self.event.to_bytes(4, "big", signed=True))
        if self.sessionId is not None:
            session_id_bytes = str.encode(self.sessionId)
            size = len(session_id_bytes).to_bytes(4, "big", signed=True)
            option_bytes.extend(size)
            option_bytes.extend(session_id_bytes)
        if self.sequence is not None:
            option_bytes.extend(self.sequence.to_bytes(4, "big", signed=True))
        return option_bytes


class Response:
    def __init__(self, header: Header, optional: Optional):
        self.optional = optional
        self.header = header
        self.payload: Union[bytes, None] = None


class TTSClient:
    def __init__(self, app_key: str, access_key: str, resource_id: str, verify_ssl: bool = True):
        self.app_key = app_key
        self.access_key = access_key
        self.resource_id = resource_id
        self.verify_ssl = verify_ssl
        self.websocket: Union[websockets.WebSocketClientProtocol, None] = None
        self.session_id: Union[str, None] = None

    async def connect(self):
        uri = "wss://voice.ap-southeast-1.bytepluses.com/api/v3/tts/bidirection"
        headers = {
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        try:
            ssl_context = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # Try different header parameter names for websockets compatibility
            try:
                self.websocket = await websockets.connect(
                    uri, 
                    additional_headers=headers,
                    ssl=ssl_context, 
                    max_size=1000000000
                )
            except TypeError:
                # Fallback to extra_headers if additional_headers is not supported
                try:
                    self.websocket = await websockets.connect(
                        uri, 
                        extra_headers=headers,
                        ssl=ssl_context, 
                        max_size=1000000000
                    )
                except TypeError:
                    # Fallback to headers parameter
                    self.websocket = await websockets.connect(
                        uri, 
                        headers=headers,
                        ssl=ssl_context, 
                        max_size=1000000000
                    )
            logger.info("Connected to TTS WebSocket service")
            await self._send_start_connection()
            
            # Wait for connection started response
            res = await self._parse_response(await self.websocket.recv())
            if res.optional.event != EVENT_ConnectionStarted:
                raise TTSConnectionError("Failed to start connection")
            logger.info("Connection started successfully")
        except Exception as e:
            raise TTSConnectionError(f"Failed to connect: {e}")

    async def disconnect(self):
        if self.websocket:
            await self._send_finish_connection()
            await self.websocket.close()
            logger.info("Disconnected from TTS WebSocket service")

    async def synthesize_text(self, text: str, speaker: str, session_id: str) -> AsyncGenerator[bytes, None]:
        if not self.websocket:
            raise TTSSessionError("Not connected to WebSocket")

        self.session_id = session_id
        await self._send_start_session(speaker)
        
        # Wait for session started response
        res = await self._parse_response(await self.websocket.recv())
        if res.optional.event != EVENT_SessionStarted:
            raise TTSSessionError("Failed to start session")
        logger.info("Session started successfully")
        
        # Send text
        await self._send_task_request(text)
        await self._send_finish_session()
        
        # Listen for audio chunks until the session is finished
        while True:
            try:
                message = await self.websocket.recv()
                response = await self._parse_response(message)
                
                if (
                    response.optional.event == EVENT_TTSResponse
                    and response.header.message_type == AUDIO_ONLY_RESPONSE
                ):
                    yield response.payload
                elif response.optional.event in [
                    EVENT_TTSSentenceStart,
                    EVENT_TTSSentenceEnd,
                ]:
                    continue
                else:
                    break
            except websockets.exceptions.ConnectionClosed:
                break

    async def stream_text(self, speaker: str, session_id: str) -> AsyncGenerator[bytes, None]:
        if not self.websocket:
            raise TTSClientError("Not connected to WebSocket")

        self.session_id = session_id
        await self._send_start_session(speaker)

        try:
            async for message in self.websocket:
                audio_chunk = await self._handle_message(message)
                if audio_chunk:
                    yield audio_chunk
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"Connection closed during streaming: {e}")

    async def send_text_for_streaming(self, text: str):
        if not self.websocket or not self.session_id:
            raise TTSSessionError("Streaming not started or not connected")
        await self._send_task_request(text)

    async def stop_streaming(self):
        if self.websocket and self.session_id:
            await self._send_finish_session()
            self.session_id = None

    async def _send_start_connection(self):
        header = Header(
            message_type=FULL_CLIENT_REQUEST,
            message_type_specific_flags=MsgTypeFlagWithEvent,
        ).as_bytes()
        optional = Optional(event=EVENT_Start_Connection).as_bytes()
        payload = str.encode("{}")
        await self._send_event_with_protocol(header, optional, payload)

    async def _send_finish_connection(self):
        header = Header(
            message_type=FULL_CLIENT_REQUEST,
            message_type_specific_flags=MsgTypeFlagWithEvent,
            serial_method=JSON,
        ).as_bytes()
        optional = Optional(event=EVENT_FinishConnection).as_bytes()
        payload = str.encode("{}")
        await self._send_event_with_protocol(header, optional, payload)

    async def _send_start_session(self, speaker: str):
        header = Header(
            message_type=FULL_CLIENT_REQUEST,
            message_type_specific_flags=MsgTypeFlagWithEvent,
            serial_method=JSON,
        ).as_bytes()
        optional = Optional(event=EVENT_StartSession, sessionId=self.session_id).as_bytes()
        payload = self._get_payload_bytes(event=EVENT_StartSession, speaker=speaker)
        await self._send_event_with_protocol(header, optional, payload)

    async def _send_finish_session(self):
        header = Header(
            message_type=FULL_CLIENT_REQUEST,
            message_type_specific_flags=MsgTypeFlagWithEvent,
            serial_method=JSON,
        ).as_bytes()
        optional = Optional(event=EVENT_FinishSession, sessionId=self.session_id).as_bytes()
        payload = str.encode("{}")
        await self._send_event_with_protocol(header, optional, payload)

    async def _send_task_request(self, text: str):
        header = Header(
            message_type=FULL_CLIENT_REQUEST,
            message_type_specific_flags=MsgTypeFlagWithEvent,
            serial_method=JSON,
        ).as_bytes()
        optional = Optional(event=EVENT_TaskRequest, sessionId=self.session_id).as_bytes()
        payload = self._get_payload_bytes(event=EVENT_TaskRequest, text=text, speaker="")
        await self._send_event_with_protocol(header, optional, payload)

    async def _send_event_with_protocol(self, header: bytes, optional: bytes = None, payload: bytes = None):
        full_client_request = bytearray(header)
        if optional is not None:
            full_client_request.extend(optional)
        if payload is not None:
            payload_size = len(payload).to_bytes(4, "big", signed=True)
            full_client_request.extend(payload_size)
            full_client_request.extend(payload)
        await self.websocket.send(full_client_request)

    def _get_payload_bytes(
        self,
        uid="1234",
        event=EVENT_NONE,
        text="",
        speaker="",
        audio_format="pcm",
        audio_sample_rate=16000,
    ):
        return str.encode(
            json.dumps(
                {
                    "user": {"uid": uid},
                    "event": event,
                    "namespace": "BidirectionalTTS",
                    "req_params": {
                        "text": text,
                        "speaker": speaker,
                        "audio_params": {
                            "format": audio_format,
                            "sample_rate": audio_sample_rate,
                        },
                    },
                }
            )
        )

    async def _parse_response(self, res) -> Response:
        if isinstance(res, str):
            raise RuntimeError(res)
        response = Response(Header(), Optional())
        # Parse result
        # header
        header = response.header
        num = 0b00001111
        header.protocol_version = res[0] >> 4 & num
        header.header_size = res[0] & 0x0F
        header.message_type = (res[1] >> 4) & num
        header.message_type_specific_flags = res[1] & 0x0F
        header.serialization_method = res[2] >> num
        header.message_compression = res[2] & 0x0F
        header.reserved = res[3]
        #
        offset = 4
        optional = response.optional
        if header.message_type == FULL_SERVER_RESPONSE or AUDIO_ONLY_RESPONSE:
            # read event
            if header.message_type_specific_flags == MsgTypeFlagWithEvent:
                optional.event = int.from_bytes(res[offset:offset+4], "big", signed=True)
                offset += 4
                if optional.event == EVENT_NONE:
                    return response
                # read connectionId
                elif optional.event == EVENT_ConnectionStarted:
                    optional.connectionId, offset = self._read_res_content(res, offset)
                elif optional.event == EVENT_ConnectionFailed:
                    optional.response_meta_json, offset = self._read_res_content(res, offset)
                elif (
                    optional.event == EVENT_SessionStarted
                    or optional.event == EVENT_SessionFailed
                    or optional.event == EVENT_SessionFinished
                ):
                    optional.sessionId, offset = self._read_res_content(res, offset)
                    optional.response_meta_json, offset = self._read_res_content(res, offset)
                else:
                    optional.sessionId, offset = self._read_res_content(res, offset)
                    response.payload, offset = self._read_res_payload(res, offset)

        elif header.message_type == ERROR_INFORMATION:
            optional.errorCode = int.from_bytes(
                res[offset : offset + 4], "big", signed=True
            )
            offset += 4
            response.payload, offset = self._read_res_payload(res, offset)
        return response

    def _read_res_content(self, res: bytes, offset: int):
        content_size = int.from_bytes(res[offset : offset + 4], "big", signed=True)
        offset += 4
        content = res[offset : offset + content_size].decode('utf-8')
        offset += content_size
        return content, offset

    def _read_res_payload(self, res: bytes, offset: int):
        payload_size = int.from_bytes(res[offset : offset + 4], "big", signed=True)
        offset += 4
        payload = res[offset : offset + payload_size]
        offset += payload_size
        return payload, offset

    async def _handle_message(self, message: Any) -> Union[bytes, None]:
        try:
            response = await self._parse_response(message)
            
            if response.header.message_type == ERROR_INFORMATION:
                raise TTSSessionError(f"TTS Error Response: {response.optional.errorCode} - {response.payload.decode('utf-8') if response.payload else 'Unknown error'}")
            
            if response.optional.event == EVENT_TTSResponse and response.header.message_type == AUDIO_ONLY_RESPONSE:
                return response.payload
            elif response.optional.event in [EVENT_TTSSentenceStart, EVENT_TTSSentenceEnd]:
                return None  # Continue processing
            elif response.optional.event == EVENT_SessionFinished:
                logger.info("Session finished successfully.")
                return b''  # Signal end of stream
            
            return None
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None