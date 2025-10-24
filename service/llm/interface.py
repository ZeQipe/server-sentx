from abc import ABC, abstractmethod
from typing import Any, Generator, Optional


class LLMProviderInterface(ABC):
    """Interface for LLM providers (Strategy pattern)"""

    @abstractmethod
    def send_message(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        file: Optional[Any] = None,
    ) -> dict[str, Any] | Generator[str, None, None]:
        """
        Send a message to the LLM provider

        Args:
            messages: List of messages with role and content
            stream: Whether to stream the response
            file: Optional file to attach

        Returns:
            Response dict or generator for streaming
        """
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """
        Validate connection to the LLM provider

        Returns:
            True if connection is valid
        """
        pass

