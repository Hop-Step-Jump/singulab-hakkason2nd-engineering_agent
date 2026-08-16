import asyncio
import concurrent.futures
import threading
from abc import ABC, abstractmethod
from typing import Optional

# Sized for a 100-agent simultaneous round against lab vLLM (I/O-bound HTTP).
LLM_THREAD_POOL_WORKERS = 128
_thread_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=LLM_THREAD_POOL_WORKERS,
    thread_name_prefix="ea-llm",
)


class LLMClient(ABC):
    def __init__(self, max_concurrency: int = 0):
        self._max_concurrency = max(0, int(max_concurrency))
        # threading.Semaphore is loop-agnostic. asyncio.Semaphore created in
        # __init__ (or bound on first asyncio.run) breaks on the next step's
        # asyncio.run — "bound to a different event loop".
        self._semaphore: Optional[threading.BoundedSemaphore] = (
            threading.BoundedSemaphore(self._max_concurrency) if self._max_concurrency > 0 else None
        )

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate text from prompt. Returns empty string on error."""
        ...

    @abstractmethod
    def check_connection(self) -> bool:
        """Check if LLM backend is reachable."""
        ...

    def _generate_limited(self, prompt: str) -> str:
        if self._semaphore is None:
            return self.generate(prompt)
        with self._semaphore:
            return self.generate(prompt)

    async def generate_async(self, prompt: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_thread_pool, self._generate_limited, prompt)
