from sqlalchemy.orm import Session
from app.database.models import BoardGame
from app.schemas.board_game import BoardGameCreate, BoardGameUpdate


def get_board_game(db: Session, board_game_id: int):
    return db.query(BoardGame).filter(BoardGame.id == board_game_id).first()


def get_board_games(db: Session, skip: int = 0, limit: int = 100):
    return db.query(BoardGame).offset(skip).limit(limit).all()


def create_board_game(db: Session, board_game: BoardGameCreate):
    # Validate max_players is greater than or equal to min_players
    if board_game.max_players < board_game.min_players:
        raise ValueError("Max players must be greater than or equal to min players")

    db_board_game = BoardGame(
        name=board_game.name,
        description=board_game.description,
        min_players=board_game.min_players,
        max_players=board_game.max_players
    )
    db.add(db_board_game)
    db.commit()
    db.refresh(db_board_game)
    return db_board_game


def update_board_game(db: Session, board_game_id: int, board_game: BoardGameUpdate):
    # Validate max_players is greater than or equal to min_players
    if board_game.max_players < board_game.min_players:
        raise ValueError("Max players must be greater than or equal to min players")

    db_board_game = db.query(BoardGame).filter(BoardGame.id == board_game_id).first()
    if db_board_game is None:
        return None

    for key, value in board_game.dict(exclude_unset=True).items():
        setattr(db_board_game, key, value)

    db.commit()
    db.refresh(db_board_game)
    return db_board_game


def delete_board_game(db: Session, board_game_id: int):
    db_board_game = db.query(BoardGame).filter(BoardGame.id == board_game_id).first()
    if db_board_game is None:
        return None

    db.delete(db_board_game)
    db.commit()
    return db_board_game
