from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database.base import get_db
from app.crud.chat_message import get_room_chat_messages
from app.middleware.auth import require_auth
from app.schemas.chat_message import ChatMessageResponse
from app.schemas.user import UserResponse

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(require_auth)],
)


@router.get("/room/{room_id}", response_model=List[ChatMessageResponse])
def get_chat_messages(
        room_id: int,
        limit: int = 50,
        db: Session = Depends(get_db)
):
    """
    Retrieve recent chat messages for a specific game room
    """
    messages = get_room_chat_messages(db, room_id, limit)

    return [
        ChatMessageResponse(
            id=msg.id,
            room_id=msg.room_id,
            user_id=msg.user_id,
            content=msg.content,
            timestamp=msg.timestamp,
            user=UserResponse(
                id=msg.user.id,
                email=msg.user.email,
                username=msg.user.username,
                is_active=msg.user.is_active,
                created_at=msg.user.created_at
            )
        ) for msg in messages
    ]