import json
import uuid
import time
from datetime import datetime
from typing import Any, Generator, Optional

import httpx
from django.conf import settings

from .interface import LLMProviderInterface


class SentXProvider(LLMProviderInterface):
    """SentX API provider implementation"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize SentX provider

        Args:
            api_key: API key for SentX (uses settings.SENTX_SECRET_KEY if not provided)
            base_url: Base URL for SentX API (uses settings.OPENAI_BASE_URL if not provided)
        """
        self.api_key = api_key or getattr(settings, "SENTX_SECRET_KEY", None) or getattr(
            settings, "OPENAI_API_KEY", None
        )
        self.base_url = (base_url or getattr(settings, "OPENAI_BASE_URL", "")).rstrip(
            "/"
        )
        self.model = getattr(settings, "OPENAI_DEFAULT_MODEL", "gpt-4")

        if not self.api_key:
            raise ValueError(
                "No API key configured. Set either SENTX_SECRET_KEY or OPENAI_API_KEY"
            )

    def validate_connection(self) -> bool:
        """Validate connection to SentX API"""
        try:
            # Simple validation - check if we can reach the API
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def send_message(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        file: Optional[Any] = None,
    ) -> dict[str, Any] | Generator[dict[str, Any], None, None]:
        """
        Send a message to SentX API (async with httpx)

        Args:
            messages: List of messages with role and content
            stream: Whether to stream the response
            file: Optional file to attach (not implemented yet)

        Returns:
            Response dict or generator for streaming
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Всегда получаем полный ответ (stream=False)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        # Logging request
        print("\n" + "=" * 80)
        print("=== SentX API Request ===")
        print(f"URL: {url}")
        print(f"Model: {self.model}")
        print(f"Messages count: {len(messages)}")
        print(f"Messages: {json.dumps(messages, ensure_ascii=False)[:500]}")
        print("=" * 80 + "\n")

        start_time = time.time()
        print(f"[LLM] Sending async request to {url}...")
        
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            elapsed = time.time() - start_time
            print(f"[LLM] Response received in {elapsed:.2f}s, status: {response.status_code}")
            
            # Логируем тело ответа при ошибке
            if response.status_code >= 400:
                print(f"[LLM] !!! ERROR RESPONSE BODY: {response.text}")
                print(f"[LLM] !!! Request payload was: {json.dumps(payload, ensure_ascii=False)[:1000]}")
            
            response.raise_for_status()
            result = response.json()
            print(f"[LLM] Response parsed. Keys: {list(result.keys())}")
            return result

    def _stream_response(
        self, url: str, headers: dict, payload: dict
    ) -> Generator[dict[str, Any], None, None]:
        """
        Stream response from SentX API

        Args:
            url: API endpoint URL
            headers: Request headers
            payload: Request payload

        Yields:
            Response chunks
        """
        response = requests.post(
            url, headers=headers, json=payload, stream=True, timeout=600
        )
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")

        if response.status_code != 200:
            print(f"!!! Non-200 status code: {response.status_code}")
            try:
                error_body = response.text[:500]
                print(f"!!! Error response body: {error_body}")
            except Exception:
                pass

        response.raise_for_status()

        # Parse SSE format
        chunk_count = 0
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if raw_line.startswith(":"):
                continue  # comment/heartbeat
            if not raw_line.startswith("data:"):
                print(f"Unexpected line format: {raw_line[:100]}")
                continue

            chunk_str = raw_line[5:].strip()
            if chunk_str == "[DONE]":
                print("Received [DONE] marker")
                break

            try:
                chunk = json.loads(chunk_str)
                chunk_count += 1

                # Log errors and first 5 chunks
                if "error" in chunk or chunk_count <= 5:
                    print(
                        f"Chunk {chunk_count}: {json.dumps(chunk, ensure_ascii=False)[:300]}"
                    )

                # Check for errors
                if "error" in chunk:
                    error_data = chunk["error"]
                    error_message = (
                        error_data
                        if isinstance(error_data, str)
                        else error_data.get("message", str(error_data))
                    )
                    print(f"!!! API ERROR: {error_message}")
                    print(f"!!! Full error chunk: {json.dumps(chunk, ensure_ascii=False)}")
                    yield {"error": error_message}
                    break

                # Skip chunks in "queued" status
                if chunk.get("status") == "queued":
                    continue

                yield chunk

            except Exception as e:
                print(f"Error processing stream chunk: {e}")
                continue

        response.close()
        print(f"Stream completed. Total chunks: {chunk_count}")

        if chunk_count == 0:
            print("!!! No chunks received from API")
            yield {"error": "No response from API"}

