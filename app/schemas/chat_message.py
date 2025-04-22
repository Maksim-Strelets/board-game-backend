from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.schemas.user import UserResponse


class ChatMessageCreate(BaseModel):
    room_id: int
    user_id: int
    content: str


class ChatMessageResponse(BaseModel):
    id: int
    room_id: int
    user_id: int
    content: str
    timestamp: datetime
    user: Optional[UserResponse] = None

    class Config:
        orm_mode = True
