"""LLM Client for streaming chat functionality."""

import json
import time
import requests
import ssl
from typing import Dict, Any, Optional, Iterator, Callable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from exceptions import LLMError, LLMResponseError, LLMConnectionError


class LLMClient:
    """Client for LLM streaming chat API."""
    
    def __init__(self, base_url: str, api_key: str):
        """
        Initialize LLM client.
        
        Args:
            base_url: Base URL for the API
            api_key: API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Apikey': api_key,
            'Content-Type': 'application/json'
        }
        
        # 创建带有重试机制的session
        self.session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        # 配置HTTP适配器
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 配置SSL
        self.session.verify = True
    
    def create_conversation(self, user_id: str, inputs: Optional[Dict[str, str]] = None) -> str:
        """
        Create a new conversation.
        
        Args:
            user_id: User identifier (1-20 characters)
            inputs: Optional variable inputs
            
        Returns:
            Conversation ID
            
        Raises:
            ValueError: If response is invalid
            requests.exceptions.RequestException: If request fails
        """
        url = f"{self.base_url}/create_conversation"
        data = {
            "UserID": user_id,
            "Inputs": inputs or {}
        }
        
        try:
            # 使用配置好的session
            response = self.session.post(
                url, 
                headers=self.headers, 
                data=json.dumps(data),
                timeout=(30, 60)  # (连接超时, 读取超时)
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise LLMConnectionError(f"Request failed: {e}")
        
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"JSON parsing failed: {e}")
        
        if "Conversation" not in result:
            raise LLMResponseError("Response missing the 'Conversation' field")
        
        if "AppConversationID" not in result["Conversation"]:
            raise LLMResponseError("Response missing the 'AppConversationID' field")
        
        return result["Conversation"]["AppConversationID"]
    
    def chat_stream(self, 
                   user_id: str, 
                   conversation_id: str, 
                   query: str,
                   files: Optional[list] = None) -> Iterator[Dict[str, Any]]:
        """
        Send a streaming chat query.
        
        Args:
            user_id: User identifier
            conversation_id: Conversation ID from create_conversation
            query: User query content
            files: Optional list of file objects
            
        Yields:
            Dict containing streaming response data
            
        Raises:
            requests.exceptions.RequestException: If request fails
        """
        url = f"{self.base_url}/chat_query_v2"
        headers = self.headers.copy()
        headers['Accept'] = 'text/event-stream'
        
        data = {
            "UserID": user_id,
            "AppConversationID": conversation_id,
            "Query": query,
            "ResponseMode": "streaming"
        }
        
        if files:
            data["QueryExtends"] = {"Files": files}
        
        try:
            # 使用配置好的session
            response = self.session.post(
                url, 
                headers=headers, 
                data=json.dumps(data), 
                stream=True,
                timeout=(30, 60)  # (连接超时, 读取超时)
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise LLMConnectionError(f"Request failed: {e}")
        
        for line in response.iter_lines(chunk_size=4):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data:"):
                    data_content = line.strip("data:").strip()
                    if data_content:
                        try:
                            yield json.loads(data_content)
                        except json.JSONDecodeError:
                            continue
    
    def chat_blocking(self, 
                     user_id: str, 
                     conversation_id: str, 
                     query: str,
                     files: Optional[list] = None) -> Dict[str, Any]:
        """
        Send a blocking chat query.
        
        Args:
            user_id: User identifier
            conversation_id: Conversation ID from create_conversation
            query: User query content
            files: Optional list of file objects
            
        Returns:
            Complete response data
            
        Raises:
            requests.exceptions.RequestException: If request fails
            ValueError: If JSON parsing fails
        """
        url = f"{self.base_url}/chat_query_v2"
        
        data = {
            "UserID": user_id,
            "AppConversationID": conversation_id,
            "Query": query,
            "ResponseMode": "blocking"
        }
        
        if files:
            data["QueryExtends"] = {"Files": files}
        
        try:
            # 使用配置好的session
            response = self.session.post(
                url, 
                headers=self.headers, 
                data=json.dumps(data),
                timeout=(30, 60)  # (连接超时, 读取超时)
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise LLMConnectionError(f"Request failed: {e}")
        
        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"JSON parsing failed: {e}")
    
    def regenerate_response(self, 
                           user_id: str, 
                           conversation_id: str, 
                           message_id: str) -> Iterator[Dict[str, Any]]:
        """
        Regenerate a response for a previous message.
        
        Args:
            user_id: User identifier
            conversation_id: Conversation ID
            message_id: Message ID to regenerate
            
        Yields:
            Dict containing streaming response data
            
        Raises:
            requests.exceptions.RequestException: If request fails
        """
        url = f"{self.base_url}/query_again"
        headers = self.headers.copy()
        headers['Accept'] = 'text/event-stream'
        
        data = {
            "AppConversationID": conversation_id,
            "MessageID": message_id,
            "UserID": user_id
        }
        
        try:
            # 使用配置好的session
            response = self.session.post(
                url, 
                headers=headers, 
                data=json.dumps(data), 
                stream=True,
                timeout=(30, 60)  # (连接超时, 读取超时)
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise LLMConnectionError(f"Request failed: {e}")
        
        for line in response.iter_lines(chunk_size=4):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data:"):
                    data_content = line.strip("data:").strip()
                    if data_content:
                        try:
                            yield json.loads(data_content)
                        except json.JSONDecodeError:
                            continue
    
    def chat_with_callback(self, 
                          user_id: str, 
                          conversation_id: str, 
                          query: str,
                          on_message: Callable[[str], None],
                          on_complete: Optional[Callable[[], None]] = None,
                          on_error: Optional[Callable[[Exception], None]] = None,
                          files: Optional[list] = None):
        """
        Send a chat query with callback functions.
        
        Args:
            user_id: User identifier
            conversation_id: Conversation ID
            query: User query content
            on_message: Callback for each message chunk
            on_complete: Optional callback when complete
            on_error: Optional callback for errors
            files: Optional list of file objects
        """
        try:
            full_message = ""
            for data in self.chat_stream(user_id, conversation_id, query, files):
                if "event" in data and data["event"] == "message":
                    chunk = data.get("answer", "")
                    full_message += chunk
                    on_message(chunk)
                elif "event" in data and data["event"] == "message_end":
                    if on_complete:
                        on_complete()
                    break
        except Exception as e:
            if on_error:
                on_error(e)
            else:
                raise