from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    
    # Default is a file in the current directory
    DATABASE_URL: str = "sqlite:///./app.db"

    # Flag: "on" (default) or "off"
    SAFETY_MODE: str = "on" 

    class Config:
        env_file = ".env"

settings = Settings()
