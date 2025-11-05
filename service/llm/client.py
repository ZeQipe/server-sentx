from typing import Any, Generator, Optional

from .interface import LLMProviderInterface


class LLMClient:
    """Client for interacting with LLM providers"""

    def __init__(self, provider: LLMProviderInterface):
        """
        Initialize LLM client

        Args:
            provider: LLM provider implementation
        """
        self.provider = provider

    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        file: Optional[Any] = None,
    ) -> dict[str, Any] | Generator[dict[str, Any], None, None]:
        """
        Send a chat message (async)

        Args:
            messages: List of messages with role and content
            stream: Whether to stream the response
            file: Optional file to attach

        Returns:
            Response dict or generator for streaming
        """
        return await self.provider.send_message(messages, stream, file)

    def validate_connection(self) -> bool:
        """
        Validate connection to the LLM provider

        Returns:
            True if connection is valid
        """
        return self.provider.validate_connection()

