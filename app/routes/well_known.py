from fastapi import APIRouter
from app.ucp.constants import UCP_A2A_EXTENSION_URI

router = APIRouter(prefix="/.well-known")

@router.get("/ucp")
async def get_ucp_profile() -> dict:
    return {
        "services": {
            "dev.ucp.shopping.a2a": {
                "endpoint": "/.well-known/agent-card.json"
            }
        }
    }

@router.get("/agent-card.json")
async def get_agent_card() -> dict:
    return {
        "kind": "AgentCard",
        "metadata": {
            "name": "UCP Checkout Agent",
            "extensions": [UCP_A2A_EXTENSION_URI]
        }
    }
