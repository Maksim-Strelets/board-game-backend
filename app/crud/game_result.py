import json
from sqlalchemy.orm import Session
from app.database.models import GameResult
from app.schemas.game_result import GameResultResponse, GameResultCreate


def save_game_result(db: Session, game_result: GameResultCreate) -> GameResult:
    """
    Create a new chat message in the database
    """
    db_obj = GameResult(
        room_id=game_result.room_id,
        final_score=json.dumps(game_result.final_score),
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def get_game_result(db: Session, room_id: int) -> GameResultResponse:
    """
    Retrieve recent chat messages for a specific room
    """
    db_obj = db.query(GameResult).filter(GameResult.room_id == room_id).first()
    return GameResultResponse(
        id=db_obj.id,
        room_id=db_obj.room_id,
        final_score=json.loads(db_obj.final_score),
        timestamp=db_obj.timestamp,
    )


def delete_game_result(db: Session, room_id: int):
    """
    Delete all chat messages for a specific room
    """
    db.query(GameResult).filter(GameResult.room_id == room_id).delete()
    db.commit()
