"""Exception classes for the HiAgent RTC SDK."""


class HiAgentSDKError(Exception):
    """Base exception for HiAgent SDK."""
    
    def __init__(self, message: str, error_code: int = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
    
    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class LLMError(HiAgentSDKError):
    """LLM related errors."""
    pass


class LLMConnectionError(LLMError):
    """LLM connection errors."""
    pass


class LLMAuthenticationError(LLMError):
    """LLM authentication errors."""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limit errors."""
    pass


class LLMResponseError(LLMError):
    """LLM response parsing errors."""
    pass


class TTSError(HiAgentSDKError):
    """TTS related errors."""
    pass


class TTSConnectionError(TTSError):
    """TTS WebSocket connection errors."""
    pass


class TTSSessionError(TTSError):
    """TTS session errors."""
    pass


class TTSAudioError(TTSError):
    """TTS audio processing errors."""
    pass


class TTSProtocolError(TTSError):
    """TTS protocol errors."""
    pass

class TTSClientError(TTSError):
    """TTS client errors."""
    pass


class DigitalHumanError(HiAgentSDKError):
    """Digital Human related errors."""
    pass


class DigitalHumanConnectionError(DigitalHumanError):
    """Digital Human WebSocket connection errors."""
    pass


class DigitalHumanLiveError(DigitalHumanError):
    """Digital Human live streaming errors."""
    pass


class DigitalHumanAuthError(DigitalHumanError):
    """Digital Human authentication errors."""
    pass


class DigitalHumanConfigError(DigitalHumanError):
    """Digital Human configuration errors."""
    pass


class RTCError(HiAgentSDKError):
    """RTC related errors."""
    pass


class RTCConnectionError(RTCError):
    """RTC connection errors."""
    pass


class RTCRoomError(RTCError):
    """RTC room errors."""
    pass


class RTCAudioError(RTCError):
    """RTC audio errors."""
    pass


# Error code mappings
LLM_ERROR_CODES = {
    4000: "Request error",
    4001: "Authentication error", 
    4002: "Rate limit exceeded",
    4003: "Too many connections",
    4004: "Conversation ID duplicate",
    4005: "Invalid conversation",
    5000: "Internal server error",
    5001: "Service unavailable",
    5002: "Server busy"
}

TTS_ERROR_CODES = {
    20000000: "Success",
    45000000: "Client error",
    55000000: "Server error",
    55000001: "Session error",
    45000001: "Invalid request parameters"
}

DIGITAL_HUMAN_ERROR_CODES = {
    1000: "Success",
    4000: "Request error",
    4001: "Authentication error",
    4002: "Concurrency limit exceeded",
    4003: "Too many connections",
    4004: "Live ID duplicate",
    4005: "RTMP address duplicate",
    4006: "Live session not found",
    4007: "Invalid interrupt",
    5000: "Live service internal error",
    5001: "Avatar service internal error",
    5002: "Server busy"
}


def get_error_message(error_code: int, service: str = "unknown") -> str:
    """Get error message for error code."""
    if service == "llm":
        return LLM_ERROR_CODES.get(error_code, f"Unknown error: {error_code}")
    elif service == "tts":
        return TTS_ERROR_CODES.get(error_code, f"Unknown error: {error_code}")
    elif service == "digital_human_develop":
        return DIGITAL_HUMAN_ERROR_CODES.get(error_code, f"Unknown error: {error_code}")
    else:
        return f"Unknown error: {error_code}"


def create_error_from_code(error_code: int, service: str, message: str = None) -> HiAgentSDKError:
    """Create appropriate error from error code."""
    error_message = message or get_error_message(error_code, service)
    
    if service == "llm":
        if error_code == 4001:
            return LLMAuthenticationError(error_message, error_code)
        elif error_code == 4002:
            return LLMRateLimitError(error_message, error_code)
        elif error_code in [4000, 4003, 4004, 4005]:
            return LLMConnectionError(error_message, error_code)
        else:
            return LLMError(error_message, error_code)
    
    elif service == "tts":
        if error_code == 55000001:
            return TTSSessionError(error_message, error_code)
        elif error_code == 45000001:
            return TTSProtocolError(error_message, error_code)
        elif error_code in [45000000, 55000000]:
            return TTSConnectionError(error_message, error_code)
        else:
            return TTSError(error_message, error_code)
    
    elif service == "digital_human_develop":
        if error_code == 4001:
            return DigitalHumanAuthError(error_message, error_code)
        elif error_code in [4000, 4002, 4003, 4004, 4005, 4006]:
            return DigitalHumanConnectionError(error_message, error_code)
        elif error_code == 4007:
            return DigitalHumanLiveError(error_message, error_code)
        elif error_code in [5000, 5001, 5002]:
            return DigitalHumanError(error_message, error_code)
        else:
            return DigitalHumanError(error_message, error_code)
    
    else:
        return HiAgentSDKError(error_message, error_code)