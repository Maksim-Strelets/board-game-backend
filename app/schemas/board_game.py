# app/schemas/board_game.py
from pydantic import BaseModel, Field

class BoardGameBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    min_players: int = Field(ge=1, le=20)
    max_players: int = Field(ge=1, le=20)

class BoardGameCreate(BoardGameBase):
    pass

class BoardGameUpdate(BoardGameBase):
    pass

class BoardGame(BoardGameBase):
    id: int

    class Config:
        orm_mode = True