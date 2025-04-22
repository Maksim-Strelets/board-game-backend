from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.routes.game_rooms_ws import broadcast_room_list_update
from app.database import models
from app.database.base import get_db
from app.crud.game_room import (
    get_game_room,
    get_game_rooms_by_game,
    create_game_room,
    update_game_room,
    delete_game_room,
    add_player_to_room,
    remove_player_from_room
)
from app.schemas.game_room import (
    GameRoom,
    GameRoomCreate,
    GameRoomUpdate,
    GameRoomPlayerResponse,
    GameRoomWithPlayers,
    GameRoomPlayerCreate,
    RoomStatus,
)
from app.schemas.user import UserResponse

router = APIRouter(
    prefix="/board-games/{game_id}/rooms",
    tags=["game-rooms"]
)


@router.post("/", response_model=GameRoom)
async def create_game_room_endpoint(game_id: int, game_room: GameRoomCreate, db: Session = Depends(get_db)):
    game_room.game_id = game_id
    try:
        room = create_game_room(db=db, game_room=game_room)
        await broadcast_room_list_update(db, game_id)
        return room
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[GameRoomWithPlayers])
def read_game_rooms(game_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    rooms = get_game_rooms_by_game(db, game_id=game_id, skip=skip, limit=limit)

    # Convert to list of GameRoomWithPlayers
    detailed_rooms = []
    for room in rooms:
        detailed_room = GameRoomWithPlayers(
            id=room.id,
            name=room.name,
            game_id=room.game_id,
            max_players=room.max_players,
            status=room.status,
            players=[
                GameRoomPlayerResponse(
                    room_id=room.id,
                    user_id=player.user_id,
                    id=player.id,
                    status=player.status,
                    user_data=UserResponse(
                        id=player.user.id,
                        email=player.user.email,
                        username=player.user.username,
                        is_active=player.user.is_active,
                        created_at=player.user.created_at,
                    )
                ) for player in room.players
            ]
        )
        detailed_rooms.append(detailed_room)

    return detailed_rooms


@router.get("/{room_id}", response_model=GameRoomWithPlayers)
def read_game_room(game_id: int, room_id: int, db: Session = Depends(get_db)):
    db_game_room = get_game_room(db, room_id=room_id)
    if db_game_room is None or db_game_room.game_id != game_id:
        raise HTTPException(status_code=404, detail="Game room not found")

    # Convert to GameRoomWithPlayers
    return GameRoomWithPlayers(
        id=db_game_room.id,
        name=db_game_room.name,
        game_id=db_game_room.game_id,
        max_players=db_game_room.max_players,
        status=db_game_room.status,
        players=[
            GameRoomPlayerResponse(
                room_id=db_game_room.id,
                user_id=player.user_id,
                id=player.id,
                status=player.status,
                user_data=UserResponse(
                    id=player.user.id,
                    email=player.user.email,
                    username=player.user.username,
                    is_active=player.user.is_active,
                    created_at=player.user.created_at,
                )
            ) for player in db_game_room.players
        ]
    )


@router.put("/{room_id}", response_model=GameRoom)
async def update_game_room_endpoint(game_id: int, room_id: int, game_room: GameRoomUpdate, db: Session = Depends(get_db)):
    # Validate room belongs to the game
    existing_room = db.query(models.GameRoom).filter(
        models.GameRoom.id == room_id,
        models.GameRoom.game_id == game_id
    ).first()
    if not existing_room:
        raise HTTPException(status_code=404, detail="Game room not found")

    updated_room = update_game_room(db=db, room_id=room_id, game_room=game_room)
    if updated_room is None:
        raise HTTPException(status_code=404, detail="Game room not found")
    await broadcast_room_list_update(db, game_id)
    return updated_room


@router.delete("/{room_id}", response_model=GameRoom)
async def delete_game_room_endpoint(game_id: int, room_id: int, db: Session = Depends(get_db)):
    # Validate room belongs to the game
    existing_room = db.query(models.GameRoom).filter(
        models.GameRoom.id == room_id,
        models.GameRoom.game_id == game_id
    ).first()
    if not existing_room:
        raise HTTPException(status_code=404, detail="Game room not found")

    deleted_room = delete_game_room(db=db, room_id=room_id)
    if deleted_room is None:
        raise HTTPException(status_code=404, detail="Game room not found")
    await broadcast_room_list_update(db, game_id)
    return deleted_room


@router.post("/{room_id}/players", response_model=GameRoomPlayerCreate)
async def add_player_endpoint(game_id: int, room_id: int, player: GameRoomPlayerCreate, db: Session = Depends(get_db)):
    # Validate room belongs to the game
    existing_room = db.query(models.GameRoom).filter(
        models.GameRoom.id == room_id,
        models.GameRoom.game_id == game_id
    ).first()
    if not existing_room:
        raise HTTPException(status_code=404, detail="Game room not found")

    try:
        result = add_player_to_room(db=db, room_id=room_id, user_id=player.user_id)
        await broadcast_room_list_update(db, game_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{room_id}/players/{user_id}", response_model=GameRoomPlayerCreate)
async def remove_player_endpoint(game_id: int, room_id: int, user_id: int, db: Session = Depends(get_db)):
    # Validate room belongs to the game
    existing_room = db.query(models.GameRoom).filter(
        models.GameRoom.id == room_id,
        models.GameRoom.game_id == game_id
    ).first()
    if not existing_room:
        raise HTTPException(status_code=404, detail="Game room not found")

    deleted_player = remove_player_from_room(db=db, room_id=room_id, user_id=user_id)
    if deleted_player is None:
        raise HTTPException(status_code=404, detail="Player not found in the room")
    await broadcast_room_list_update(db, game_id)
    return deleted_player
