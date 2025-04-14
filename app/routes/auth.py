# app/routes/auth.py
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.crud.user import create_user, get_user_by_username, get_user
from app.schemas.token import TokenResponse, TokenRefreshRequest
from app.schemas.user import UserCreate, UserResponse, Token
from app.utils.security import verify_password, create_access_token, create_refresh_token, decode_token, \
    is_token_expired, is_refresh_token
from app.config import settings

router = APIRouter()


@router.post("/register", response_model=UserResponse)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    user = create_user(db=db, user=user)
    return dict(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )

@router.post("/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = get_user_by_username(db, username=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data=dict(
            id=user.id,
            username=user.username,
            email=user.email,

        )
    )
    _refresh_token = create_refresh_token({"sub": str(user.id)})
    return {
        "access_token": access_token,
        "refresh_token": _refresh_token,
        "token_type": "bearer"
    }


# Add this endpoint to your router
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
        response: Response,
        db: Session = Depends(get_db),
        refresh_request: TokenRefreshRequest = None,
        refresh_token: Optional[str] = Cookie(None),
):
    """
    Endpoint to refresh an access token using a refresh token.
    The refresh token can be provided in the request body or as a cookie.
    """
    # Use token from request body or cookie
    token = refresh_request.refresh_token if refresh_request and refresh_request.refresh_token else refresh_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required"
        )

    try:
        # Verify it's a refresh token and not expired
        if not is_refresh_token(token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )

        if is_token_expired(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired"
            )

        # Decode the token to get the user id
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id or not str(user_id).isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token"
            )

        user = get_user(db, int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found"
            )

        # Create new tokens
        access_token = create_access_token(data=dict(
            id=user.id,
            username=user.username,
            email=user.email,

        ))

        # Create a new refresh token (token rotation)
        refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        new_refresh_token = create_refresh_token(
            data={"sub": str(user_id)},
            expires_delta=refresh_token_expires
        )

        # Set refresh token as httpOnly cookie
        max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=not settings.DEBUG,  # Secure in production
            samesite="lax",
            max_age=max_age
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_DAYS * 60 * 60 * 24,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not validate token: {str(e)}"
        )
