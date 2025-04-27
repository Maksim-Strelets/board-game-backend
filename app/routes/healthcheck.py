from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud.board_game import get_board_games
from app.database.base import get_db

router = APIRouter()


@router.get("/healthcheck", response_model=dict[str, str])
def healthcheck(limit: int = 1, db: Session = Depends(get_db)):
    get_board_games(db, limit=limit)
    return dict(status="ok")

