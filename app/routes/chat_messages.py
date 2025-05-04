from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database.base import get_db
from app.crud.chat_message import get_room_chat_messages
from app.middleware.auth import get_current_user_id
from app.schemas.chat_message import ChatMessageResponse
from app.serializers.user import serialize_user

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.get("/room/{room_id}", response_model=List[ChatMessageResponse])
def get_chat_messages(
        room_id: int,
        limit: int = 50,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
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
            user=serialize_user(msg.user)
        ) for msg in messages
    ]
