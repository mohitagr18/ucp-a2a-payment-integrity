from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routes import well_known, a2a_rpc

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB tables
    # This calls the init_db() method on the global singletons defined in a2a_rpc
    await a2a_rpc.store.init_db()
    await a2a_rpc.idempotency_store.init_db()
    yield
    # Shutdown (optional cleanup)

def create_app() -> FastAPI:
    app = FastAPI(title="UCP A2A Agent", lifespan=lifespan)
    app.include_router(well_known.router)
    app.include_router(a2a_rpc.router)
    return app
