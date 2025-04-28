from typing import Optional, Callable, Dict, Any
import jwt
from jwt.exceptions import PyJWTError, ExpiredSignatureError
import logging
from fastapi import Request, HTTPException, status, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import aiohttp
from urllib.parse import urljoin

from app.config import settings
from app.database.base import get_db
from app.crud.user import get_user
from app.utils.security import is_token_expired

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to authenticate requests using JWT tokens with reactive token renewal"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip auth for OPTIONS requests and public endpoints
        if request.method == "OPTIONS" or self._is_public_endpoint(request.url.path):
            return await call_next(request)

        # Get token from Authorization header
        access_token = self._get_token_from_header(request)
        refresh_token = self._get_refresh_token_from_cookie(request)

        # Initialize request state
        request.state.user_id = None
        request.state.token_renewed = False

        if access_token:
            try:
                # Verify and decode token
                payload = jwt.decode(
                    access_token,
                    settings.SECRET_KEY,
                    algorithms=[settings.ALGORITHM]
                )
                user_id = payload.get("id")

                if user_id:
                    # Store user_id in request state
                    request.state.user_id = int(user_id)

                    # Check if user exists (optional, can be resource-intensive)
                    if settings.AUTH_VALIDATE_USER_EXISTS:
                        db = next(get_db())
                        try:
                            user = get_user(db, int(user_id))
                            if not user or not user.is_active:
                                logger.warning(f"User {user_id} not found or inactive")
                                request.state.user_id = None
                        finally:
                            db.close()

            except ExpiredSignatureError:
                # Token is expired but valid, try to renew it if we have a refresh token
                logger.info("Access token expired, attempting renewal")
                if refresh_token:
                    new_tokens = await self._renew_token(refresh_token)
                    if new_tokens:
                        logger.info("Successfully renewed access token")
                        # Extract user_id from the new token
                        try:
                            new_payload = jwt.decode(
                                new_tokens["access_token"],
                                settings.SECRET_KEY,
                                algorithms=[settings.ALGORITHM]
                            )
                            request.state.user_id = int(new_payload.get("sub"))
                            request.state.token_renewed = True
                            request.state.new_tokens = new_tokens
                        except PyJWTError as e:
                            logger.error(f"Error decoding new token: {e}")
                    else:
                        logger.warning("Token renewal failed")
                else:
                    logger.warning("Access token expired and no refresh token provided")

            except PyJWTError as e:
                logger.warning(f"Invalid authentication token: {e}")

            except Exception as e:
                logger.error(f"Authentication error: {e}")

        # Process the request
        response = await call_next(request)

        # If token was renewed, update the response with new tokens
        if getattr(request.state, "token_renewed", False) and hasattr(request.state, "new_tokens"):
            # Add the new access token to the response headers
            response.headers["X-New-Access-Token"] = request.state.new_tokens["access_token"]

            # Set the new refresh token as a cookie
            if "refresh_token" in request.state.new_tokens:
                max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
                response.set_cookie(
                    key="refresh_token",
                    value=request.state.new_tokens["refresh_token"],
                    httponly=True,
                    secure=not settings.DEBUG,  # Secure in production
                    samesite="lax",
                    max_age=max_age
                )

        return response

    def _get_token_from_header(self, request: Request) -> Optional[str]:
        """Extract token from the Authorization header"""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        return auth_header.split(" ")[1]

    def _get_refresh_token_from_cookie(self, request: Request) -> Optional[str]:
        """Extract refresh token from cookies"""
        return request.cookies.get("refresh_token")

    async def _renew_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Attempt to renew an access token using a refresh token"""
        try:
            # Check if refresh token is valid before making the request
            if is_token_expired(refresh_token):
                logger.warning("Refresh token is expired, renewal skipped")
                return None

            # Make a request to the token refresh endpoint
            async with aiohttp.ClientSession() as session:
                refresh_url = urljoin(settings.API_URL, "/auth/refresh")
                headers = {"Content-Type": "application/json"}
                data = {"refresh_token": refresh_token}

                async with session.post(refresh_url, headers=headers, json=data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Token refresh failed with status {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Error during token renewal: {e}")
            return None

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if the endpoint is public (no auth required)"""
        public_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/auth/login",
            "/auth/register",
            "/auth/refresh",
        ]

        # Check exact matches
        if path in public_paths:
            return True

        # Check if path starts with any public prefix
        for public_path in public_paths:
            if path.startswith(public_path):
                return True

        return False


def get_current_user_id(request: Request):
    """Dependency to enforce authentication on routes"""
    if not hasattr(request.state, "user_id") or request.state.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"Authenticate": "Bearer"},
        )
    return request.state.user_id
