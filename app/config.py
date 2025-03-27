# app/config.py
from pydantic_settings import BaseSettings
from envparse import env

env.read_envfile()


class Settings(BaseSettings):
    DATABASE_URL: str = env("DATABASE_URL", "postgresql://user:password@localhost/boardgamedb")
    SECRET_KEY: str = env("SECRET_KEY", "your-secret-key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # HOST
    HOST: str = env("HOST", "localhost")
    PORT: str = env("PORT", "8000")
    RELOAD: bool = env.bool("RELOAD", default=False)

    # CORS Settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",  # React default
        "http://127.0.0.1:3000",
        "https://localhost:3000",
        "http://localhost:8000",  # Potential backend dev server
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]


settings = Settings()
