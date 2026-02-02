from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    
    # Persistence (Used in Phase 3)
    # Default is a file in the current directory
    DATABASE_URL: str = "sqlite:///./app.db"

    class Config:
        env_file = ".env"

settings = Settings()
