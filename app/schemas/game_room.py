# app/schemas/game_room.py
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class RoomStatus(str, Enum):
    WAITING = "waiting"
    STARTED = "started"
    ENDED = "ended"

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

class GameRoomPlayerCreate(GameRoomPlayerBase):
    pass

class GameRoomPlayerResponse(GameRoomPlayerBase):
    id: int

    class Config:
        orm_mode = True

class GameRoomWithPlayers(GameRoom):
    players: List[GameRoomPlayerResponse] = []