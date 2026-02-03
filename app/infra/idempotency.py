from typing import Protocol, Dict, Optional, Any
from dataclasses import dataclass
import json
import aiosqlite

@dataclass(frozen=True)
class IdempotencyKey:
    context_id: str
    message_id: str
    action: str 

class IdempotencyStore(Protocol):
    async def get(self, key: IdempotencyKey) -> Optional[Dict[str, Any]]: ...
    async def put(self, key: IdempotencyKey, response_payload: Dict[str, Any]) -> None: ...

class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self):
        self._store: Dict[int, Dict[str, Any]] = {}
    async def get(self, key: IdempotencyKey) -> Optional[Dict[str, Any]]:
        return self._store.get(hash(key))
    async def put(self, key: IdempotencyKey, response_payload: Dict[str, Any]) -> None:
        self._store[hash(key)] = response_payload

class SQLiteIdempotencyStore(IdempotencyStore):
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS idempotency (
                    key_hash TEXT PRIMARY KEY,
                    context_id TEXT,
                    message_id TEXT,
                    action TEXT,
                    response_json TEXT
                )
            """)
            await db.commit()

    def _hash_key(self, key: IdempotencyKey) -> str:
        # Simple string representation for unique constraint
        return f"{key.context_id}::{key.message_id}::{key.action}"

    async def get(self, key: IdempotencyKey) -> Optional[Dict[str, Any]]:
        k = self._hash_key(key)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT response_json FROM idempotency WHERE key_hash=?", (k,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
        return None

    async def put(self, key: IdempotencyKey, response_payload: Dict[str, Any]) -> None:
        k = self._hash_key(key)
        payload_json = json.dumps(response_payload)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO idempotency (key_hash, context_id, message_id, action, response_json) VALUES (?, ?, ?, ?, ?)",
                (k, key.context_id, key.message_id, key.action, payload_json)
            )
            await db.commit()
