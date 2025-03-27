# app/database/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum


class RoomStatus(enum.Enum):
    WAITING = "waiting"
    STARTED = "started"
    ENDED = "ended"


class PlayerStatus(enum.Enum):
    READY = "ready"
    NOT_READY = "not_ready"


Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BoardGame(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    min_players = Column(Integer, nullable=False)
    max_players = Column(Integer, nullable=False)
    hidden = Column(Boolean, nullable=False, default=False)

    # Add relationship to game rooms
    rooms = relationship("GameRoom", back_populates="game")


class GameRoom(Base):
    __tablename__ = "game_rooms"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    name = Column(String, nullable=False)
    max_players = Column(Integer, nullable=False)
    status = Column(Enum(RoomStatus), default=RoomStatus.WAITING, nullable=False)

    # Relationship to board game
    game = relationship("BoardGame", back_populates="rooms")

    # Relationship to players in the room
    players = relationship("GameRoomPlayer", back_populates="room")

    def __repr__(self):
        return f"<GameRoom(id={self.id}, name='{self.name}', game_id={self.game_id})>"


class GameRoomPlayer(Base):
    __tablename__ = "game_room_players"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(PlayerStatus), default=PlayerStatus.NOT_READY, nullable=False)

    # Relationships
    room = relationship("GameRoom", back_populates="players")
    user = relationship("User")  # Assuming User model exists

    def __repr__(self):
        return f"<GameRoomPlayer(room_id={self.room_id}, user_id={self.user_id})>"
