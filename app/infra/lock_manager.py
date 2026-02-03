import asyncio
from typing import Protocol, Dict
from contextlib import asynccontextmanager

class LockManager(Protocol):
    def lock(self, key: str):
        """Returns an async context manager for the given key."""
        ...

class InMemoryLockManager(LockManager):
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    @asynccontextmanager
    async def lock(self, key: str):
        # 1. Get or create the lock for this specific ID safely
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            lock_instance = self._locks[key]
        
        # 2. Acquire the lock
        async with lock_instance:
            yield
