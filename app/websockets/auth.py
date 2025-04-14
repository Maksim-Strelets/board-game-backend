# app/websockets/auth.py
from fastapi import WebSocket, status
from typing import Optional, Callable, Dict, Any
import jwt
from jwt.exceptions import PyJWTError

from app.config import settings
from app.database.base import get_db
from app.crud.user import get_user
import logging

logger = logging.getLogger(__name__)


class WebSocketAuthMiddleware:
    """Middleware to handle authentication for WebSocket connections"""

    async def authenticate(self, websocket: WebSocket) -> Optional[int]:
        """
        Authenticate a WebSocket connection using JWT token.
        Returns the authenticated user_id or None if authentication fails.
        """
        # Get auth header (WebSocket doesn't support regular headers, but the info is accessible)
        # The format is usually "Authorization: Bearer <token>"
        token = websocket.query_params.get('token', '')

        if not token:
            logger.warning("No authentication token provided in WebSocket connection")
            return None

        try:
            # Decode JWT token
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            user_id: int = payload.get("id")

            if user_id is None:
                logger.warning("Invalid authentication token - missing user ID")
                return None

            # Verify user exists in database
            db = next(get_db())
            user = get_user(db, user_id)
            db.close()

            if not user or not user.is_active:
                logger.warning(f"User {user_id} not found or inactive")
                return None
            return user_id

        except PyJWTError as e:
            logger.warning(f"JWT token validation failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None


# Create singleton instance
websocket_auth = WebSocketAuthMiddleware()