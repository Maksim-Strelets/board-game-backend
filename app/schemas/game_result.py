from pydantic import BaseModel
from datetime import datetime


class GameResultCreate(BaseModel):
    room_id: int
    final_score: dict


class GameResultResponse(BaseModel):
    id: int
    room_id: int
    final_score: dict
    timestamp: datetime

    class Config:
        orm_mode = True
