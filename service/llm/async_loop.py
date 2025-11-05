"""
Global async event loop for parallel LLM requests
"""
import asyncio
import threading
from typing import Optional


class GlobalAsyncLoop:
    """Singleton для глобального async event loop"""
    
    _instance: Optional['GlobalAsyncLoop'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._start_loop()
    
    def _start_loop(self):
        """Запускаем event loop в отдельном потоке"""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            print("[ASYNC_LOOP] Event loop started in background thread")
            self._loop.run_forever()
        
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        
        # Ждём пока loop создастся
        while self._loop is None:
            import time
            time.sleep(0.01)
    
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Получить event loop"""
        if self._loop is None:
            raise RuntimeError("Event loop not initialized")
        return self._loop
    
    def run_coroutine(self, coro):
        """
        Запустить корутину в глобальном event loop
        Возвращает Future
        """
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


# Глобальный экземпляр
_global_loop = GlobalAsyncLoop()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """Получить глобальный event loop"""
    return _global_loop.loop


def run_async(coro):
    """
    Запустить корутину асинхронно и дождаться результата
    
    Args:
        coro: Корутина для выполнения
        
    Returns:
        Результат выполнения корутины
    """
    future = _global_loop.run_coroutine(coro)
    return future.result()

