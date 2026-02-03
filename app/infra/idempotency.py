from typing import Protocol, Dict, Optional, Any
from dataclasses import dataclass

@dataclass(frozen=True)
class IdempotencyKey:
    context_id: str
    message_id: str
    # 'action' helps distinguish different intents within a message if needed,
    # but A2A usually keys strictly on messageId. 
    # We include it to be safe if a message has multiple data parts.
    action: str 

class IdempotencyStore(Protocol):
    async def get(self, key: IdempotencyKey) -> Optional[Dict[str, Any]]:
        """Returns the saved response payload if this key was already processed."""
        ...

    async def put(self, key: IdempotencyKey, response_payload: Dict[str, Any]) -> None:
        """Saves the response payload for a processed key."""
        ...

class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self):
        # Maps hash(IdempotencyKey) -> response_dict
        self._store: Dict[int, Dict[str, Any]] = {}

    async def get(self, key: IdempotencyKey) -> Optional[Dict[str, Any]]:
        return self._store.get(hash(key))

    async def put(self, key: IdempotencyKey, response_payload: Dict[str, Any]) -> None:
        self._store[hash(key)] = response_payload
