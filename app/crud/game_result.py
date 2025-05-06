import json
from sqlalchemy.orm import Session
from app.database.models import GameResult
from app.schemas.game_result import (
    GameResultResponse,
    GameResultCreate,
    GameStateCreate,
    GameStateResponse,
)


def save_game_result(db: Session, game_result: GameResultCreate) -> GameResult:
    """
    Create a new chat message in the database
    """
    # Check if a record already exists for this room
    db_obj = db.query(GameResult).filter(GameResult.room_id == game_result.room_id).first()

    if db_obj:
        # Update existing record
        db_obj.final_score = json.dumps(game_result.final_score)
    else:
        # Create new record
        db_obj = GameResult(
            room_id=game_result.room_id,
            final_score=json.dumps(game_result.final_score),
        )
        db.add(db_obj)

    # Commit changes and refresh object
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


def dump_game_state(db: Session, game: GameStateCreate) -> GameResult:
    """
    Create a new game state record or update an existing one for the room

    Args:
        db: Database session
        game: Game state information to save

    Returns:
        Updated or created GameResult object
    """
    # Check if a record already exists for this room
    db_obj = db.query(GameResult).filter(GameResult.room_id == game.room_id).first()

    if db_obj:
        # Update existing record
        db_obj.game_state = json.dumps(game.state)
    else:
        # Create new record
        db_obj = GameResult(
            room_id=game.room_id,
            game_state=json.dumps(game.state),
        )
        db.add(db_obj)

    # Commit changes and refresh object
    db.commit()
    db.refresh(db_obj)
    return db_obj


def load_game_state(db: Session, room_id: int) -> GameStateResponse:
    """
    Retrieve recent chat messages for a specific room
    """
    db_obj = db.query(GameResult).filter(GameResult.room_id == room_id).first()
    return GameStateResponse(
        id=db_obj.id,
        room_id=db_obj.room_id,
        state=json.loads(db_obj.game_state),
        timestamp=db_obj.timestamp,
    )
