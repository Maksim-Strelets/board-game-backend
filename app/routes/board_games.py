from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.base import get_db
from app.crud.board_game import (
    get_board_game,
    get_board_games,
    create_board_game,
    update_board_game,
    delete_board_game
)
from app.schemas.board_game import BoardGame, BoardGameCreate, BoardGameUpdate

router = APIRouter(
    prefix="/board-games",
    tags=["board-games"]
)


@router.post("/", response_model=BoardGame)
def create_board_game_endpoint(board_game: BoardGameCreate, db: Session = Depends(get_db)):
    try:
        return create_board_game(db=db, board_game=board_game)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[BoardGame])
def read_board_games(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    board_games = get_board_games(db, skip=skip, limit=limit)
    return board_games


@router.get("/{board_game_id}", response_model=BoardGame)
def read_board_game(board_game_id: int, db: Session = Depends(get_db)):
    db_board_game = get_board_game(db, board_game_id=board_game_id)
    if db_board_game is None:
        raise HTTPException(status_code=404, detail="Board game not found")
    return db_board_game


@router.put("/{board_game_id}", response_model=BoardGame)
def update_board_game_endpoint(board_game_id: int, board_game: BoardGameUpdate, db: Session = Depends(get_db)):
    try:
        updated_board_game = update_board_game(db=db, board_game_id=board_game_id, board_game=board_game)
        if updated_board_game is None:
            raise HTTPException(status_code=404, detail="Board game not found")
        return updated_board_game
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{board_game_id}", response_model=BoardGame)
def delete_board_game_endpoint(board_game_id: int, db: Session = Depends(get_db)):
    deleted_board_game = delete_board_game(db=db, board_game_id=board_game_id)
    if deleted_board_game is None:
        raise HTTPException(status_code=404, detail="Board game not found")
    return deleted_board_game
