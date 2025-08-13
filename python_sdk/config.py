class DigitalHumanConfig:
    APPID = "it31vjg0vbdp693s"
    TOKEN = "4mVUjkuhInJUjOHZhz13MIS6NXEixvCw"
    ROLE = "250623-zhibo-linyunzhi"

    RTC_APP_ID = "688c22d8ee6d34017663be07"
    RTC_ROOM_ID = "hi_agent_tta_demo"
    RTC_UID = "digital_human_develop"
    RTC_TOKEN = "001688c22d8ee6d34017663be07XADCE+4Ad3+caPe5pWgRAGhpX2FnZW50X3R0YV9kZW1vFQBkaWdpdGFsX2h1bWFuX2RldmVsb3AGAAAA97mlaAEA97mlaAIA97mlaAMA97mlaAQA97mlaAUA97mlaCAAz0YmAk9PKM8F4zfZb5KwnOD2WdsTotEWE0w1I5A6K0k="


class STTConfig:
    """STT (Speech-to-Text) configuration."""
    # 认证信息 - 使用参考代码中的有效配置
    APP_KEY = "5182023671"
    ACCESS_KEY = "fm8FnSDJJWVlPm3Tq0YWERFtPNefnyAs"
    RESOURCE_ID = "volc.bigasr.sauc.duration"
    
    # WebSocket服务URL
    STREAM_URL = "wss://voice.ap-southeast-1.bytepluses.com/api/v3/sauc/bigmodel"
    
    # 音频处理配置
    SAMPLE_RATE = 16000
    CHANNELS = 1
    BITS = 16
    AUDIO_FORMAT = "wav"
    SEGMENT_DURATION = 200  # ms
    CHUNK_SIZE = 1024
    
    # 模型配置
    MODEL_NAME = "bigmodel"
    ENABLE_PUNCTUATION = True
    ENABLE_ITN = True
    ENABLE_DDC = True
    SHOW_UTTERANCES = True
    ENABLE_NONSTREAM = False
    
    # 连接配置
    VERIFY_SSL = True
    TIMEOUT = 30
    MAX_RETRIES = 3
    PING_INTERVAL = 30
    PING_TIMEOUT = 10
    CLOSE_TIMEOUT = 10
    
    # 重连配置
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_DELAY = 1.0
    HEARTBEAT_INTERVAL = 30
    HEALTH_CHECK_TIMEOUT = 5.0


class TTSConfig:
    APPKEY = "1412254860"
    ACCESS_KEY = "toY4OciNOPoxaa4Czds2WldMIcTIhv6C"
    RESOURCE_ID = "volc.service_type.1000009"


class HiAgentConfig:
    BASE_URL = "https://hiagent.volcenginepaas.com/api/proxy/api/v1"
    API_KEY = "d262djub2no6qhvbn6o0"
    # BASE_URL = "https://hiagent-byteplus.volcenginepaas.com"
    # API_KEY = "your_hiagent_api_key"
    # APP_ID = "cv3bj7kfl93b530qj2n0"

