# app/utils/security.py
from typing import Dict, Any, Optional

import jwt
from jwt import PyJWTError
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT refresh token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire})
    to_encode.update({"token_type": "refresh"})  # Mark as refresh token

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode a JWT token without verifying expiration
    """
    # Set verify_exp=False to decode even if expired
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_exp": False}
    )
    return payload


def is_token_expired(token: str) -> bool:
    """
    Check if a token is expired
    """
    try:
        payload = decode_token(token)
        expiration = datetime.fromtimestamp(payload.get("exp", 0))
        return datetime.utcnow() > expiration
    except Exception as e:
        return True


def is_refresh_token(token: str) -> bool:
    """
    Check if a token is a refresh token
    """
    try:
        payload = decode_token(token)
        return payload.get("token_type") == "refresh"
    except Exception as e:
        return False
