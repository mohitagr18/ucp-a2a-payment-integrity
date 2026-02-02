from fastapi import FastAPI
from app.routes import well_known, a2a_rpc

def create_app() -> FastAPI:
    app = FastAPI(title="UCP A2A Agent")
    app.include_router(well_known.router)
    app.include_router(a2a_rpc.router)
    return app
