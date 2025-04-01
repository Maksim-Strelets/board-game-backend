# app/crud/game_room.py
from sqlalchemy.orm import Session, joinedload
from app.database.models import GameRoom, GameRoomPlayer, RoomStatus, BoardGame, PlayerStatus
from app.schemas.game_room import GameRoomCreate, GameRoomUpdate, RoomStatus as SchemaRoomStatus


def get_game_room(db: Session, room_id: int):
    return db.query(GameRoom).options(joinedload(GameRoom.players)).filter(GameRoom.id == room_id).first()


def get_game_rooms_by_game(db: Session, game_id: int, skip: int = 0, limit: int = 100):
    return (db.query(GameRoom)
            .filter(GameRoom.game_id == game_id)
            .filter(GameRoom.status != RoomStatus.ENDED.name)
            .offset(skip)
            .limit(limit)
            .all())


def create_game_room(db: Session, game_room: GameRoomCreate):
    # Validate that the game exists
    game = db.query(BoardGame).filter(BoardGame.id == game_room.game_id).first()
    if not game:
        raise ValueError("Game not found")

    # Validate max players against game's player limits
    if game_room.max_players < game.min_players or game_room.max_players > game.max_players:
        raise ValueError(f"Players must be between {game.min_players} and {game.max_players}")

    db_game_room = GameRoom(
        name=game_room.name,
        game_id=game_room.game_id,
        max_players=game_room.max_players,
        status=game_room.status.name
    )
    db.add(db_game_room)
    db.commit()
    db.refresh(db_game_room)
    return db_game_room


def update_game_room(db: Session, room_id: int, game_room: GameRoomUpdate):
    db_game_room = db.query(GameRoom).filter(GameRoom.id == room_id).first()
    if db_game_room is None:
        return None

    # Update fields if provided
    if game_room.name is not None:
        db_game_room.name = game_room.name

    if game_room.max_players is not None:
        # Optional: Add validation if needed
        db_game_room.max_players = game_room.max_players

    if game_room.status is not None:
        db_game_room.status = game_room.status.name

    db.commit()
    db.refresh(db_game_room)
    return db_game_room


def delete_game_room(db: Session, room_id: int):
    db_game_room = db.query(GameRoom).filter(GameRoom.id == room_id).first()
    if db_game_room is None:
        return None

    db.delete(db_game_room)
    db.commit()
    return db_game_room


def add_player_to_room(db: Session, room_id: int, user_id: int):
    # Check if room exists
    room = db.query(GameRoom).filter(GameRoom.id == room_id).first()
    if not room:
        raise ValueError("Room not found")

    # Check if room is still accepting players
    if room.status != RoomStatus.WAITING:
        raise ValueError("Cannot join a room that is not in waiting status")

    # Check if room is full
    current_players = db.query(GameRoomPlayer).filter(GameRoomPlayer.room_id == room_id).count()
    if current_players >= room.max_players:
        raise ValueError("Room is full")

    # Check if user is already in the room
    existing_player = db.query(GameRoomPlayer).filter(
        GameRoomPlayer.room_id == room_id,
        GameRoomPlayer.user_id == user_id
    ).first()
    if existing_player:
        return existing_player

    # Create new room player
    db_room_player = GameRoomPlayer(
        room_id=room_id,
        user_id=user_id,
        status=PlayerStatus.NOT_READY,
    )
    db.add(db_room_player)
    db.commit()
    db.refresh(db_room_player)
    return db_room_player


def get_room_player(db: Session, room_id: int, user_id: int):
    return db.query(GameRoomPlayer).filter(
        GameRoomPlayer.room_id == room_id,
        GameRoomPlayer.user_id == user_id
    ).first()


def update_player_status(
    db: Session,
    room_id: int,
    user_id: int,
    new_status: PlayerStatus
):
    # Find the player in the room
    db_room_player = db.query(GameRoomPlayer).filter(
        GameRoomPlayer.room_id == room_id,
        GameRoomPlayer.user_id == user_id
    ).first()

    if db_room_player is None:
        raise ValueError("Player not found in room")

    # Update player status
    db_room_player.status = new_status.name
    db.commit()
    db.refresh(db_room_player)
    return db_room_player


def remove_player_from_room(db: Session, room_id: int, user_id: int):
    db_room_player = db.query(GameRoomPlayer).filter(
        GameRoomPlayer.room_id == room_id,
        GameRoomPlayer.user_id == user_id
    ).first()

    if db_room_player is None:
        return None

    db.delete(db_room_player)
    db.commit()
    return db_room_player