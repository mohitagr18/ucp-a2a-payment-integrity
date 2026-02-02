from typing import Literal, Any
from pydantic import BaseModel

class A2APart(BaseModel):
    kind: Literal["text", "data"]
    text: str | None = None
    data: dict[str, Any] | None = None

class A2AMessage(BaseModel):
    kind: Literal["message"]
    role: Literal["user", "agent"]
    messageId: str
    contextId: str
    parts: list[A2APart]
