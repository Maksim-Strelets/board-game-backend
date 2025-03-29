# app/schemas/game_room.py
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

from app.schemas.user import UserResponse

class RoomStatus(str, Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"


class PlayerStatus(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    IN_GAME = "in_game"


class GameRoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    game_id: int
    max_players: int = Field(ge=2, le=20)
    status: RoomStatus = RoomStatus.WAITING

class GameRoomCreate(GameRoomBase):
    pass

class GameRoomUpdate(BaseModel):
    name: Optional[str] = None
    max_players: Optional[int] = None
    status: Optional[RoomStatus] = None

class GameRoom(GameRoomBase):
    id: int

    class Config:
        orm_mode = True

class GameRoomPlayerBase(BaseModel):
    room_id: int
    user_id: int
    status: Optional[PlayerStatus] = None

class GameRoomPlayerCreate(GameRoomPlayerBase):
    pass

class GameRoomPlayerResponse(GameRoomPlayerBase):
    id: int
    user_data: UserResponse

    class Config:
        orm_mode = True

class GameRoomWithPlayers(GameRoom):
    players: List[GameRoomPlayerResponse] = []