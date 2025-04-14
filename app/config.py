# app/config.py
from pydantic_settings import BaseSettings
from envparse import env

env.read_envfile()


class Settings(BaseSettings):
    DEBUG: bool = True
    DATABASE_URL: str = env("DATABASE_URL", "postgresql://user:password@localhost/boardgamedb")

    # HOST
    HOST: str = env("HOST", "localhost")
    PORT: str = env("PORT", "8000")
    RELOAD: bool = env.bool("RELOAD", default=False)

    # CORS Settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://10.200.39.74:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Authentication settings
    SECRET_KEY: str = "your-secret-key-change-in-production"  # Change this in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60

    # Whether to validate that the user exists in the database for every request
    # Setting to False improves performance but reduces security slightly
    AUTH_VALIDATE_USER_EXISTS: bool = False


settings = Settings()
