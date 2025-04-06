# app/games/abstract_game.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional

from fastapi.encoders import jsonable_encoder

from app.crud.game_room import update_game_room, get_game_room, update_player_status
from app.crud.user import get_user
from app.database.models import RoomStatus, PlayerStatus
from app.schemas.game_room import GameRoomUpdate
from app.serializers.user import serialize_user
from app.websockets.manager import ConnectionManager, WebSocketMessageType, GameWebSocketMessageType, WebSocketMessage


class AbstractGameManager(ABC):
    """Abstract base class for all game managers."""

    def __init__(self, db, room, connection_manager: ConnectionManager):
        self.db = db
        self.pending_requests = {}
        self.connection_manager = connection_manager
        self.room_id = room.id
        self.players = {player.user_id: player for player in room.players}
        self.game_state = {}
        self.current_player_index = 0
        self.is_game_over = False
        self.winner = None

    @abstractmethod
    async def initialize_game(self) -> Dict[str, Any]:
        """Initialize game state and return initial state."""
        pass

    async def process_move(self, player_id: int, move_data: Dict[str, Any]) -> None:
        """
        Process a move from a player.

        Args:
            player_id: ID of the player making the move
            move_data: Dictionary containing move information

        Returns:
            Tuple of (success, error_message, updated_state)
        """
        # Process the move
        room = get_game_room(self.db, self.room_id)
        user = get_user(self.db, player_id)
        user_public = serialize_user(user)
        success, error_message, is_game_over = await self._process_move(player_id, move_data)

        if not success:
            await self.connection_manager.send(self.room_id, player_id, {
                "type": "game_error",
                "message": error_message
            })
            return

        # Check if game is over and send stats
        if not is_game_over:
            return

        # Get game stats
        game_stats = self.get_game_stats()

        # Broadcast game ended with stats
        await self.connection_manager.broadcast(self.room_id, {
            "type": "game_ended",
            "stats": jsonable_encoder(game_stats)
        })

        # Update room status to completed
        update_game_room(self.db, self.room_id, GameRoomUpdate(status=RoomStatus.ENDED))

        # Broadcast room status changed
        status_message = WebSocketMessage(
            type=WebSocketMessageType.ROOM_STATUS_CHANGED,
            user_id=player_id,
            room_id=self.room_id,
            user=user_public,
            content={
                "status": RoomStatus.ENDED.value
            }
        )
        await self.connection_manager.broadcast(self.room_id, status_message.to_dict())

        # Update player statuses
        for player in room.players:
            new_status = PlayerStatus.NOT_READY
            updated_player = update_player_status(self.db, self.room_id, player.user_id, new_status)
            status_change_message = WebSocketMessage(
                type=WebSocketMessageType.PLAYER_STATUS_CHANGED,
                user_id=player.user_id,
                room_id=self.room_id,
                user=user_public,
                content={
                    "player": jsonable_encoder(updated_player),
                    "status": new_status.value
                }
            )
            await self.connection_manager.broadcast(self.room_id, status_change_message.to_dict())

    @abstractmethod
    async def _process_move(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], bool]:
        """
        Process a move from a player.

        Args:
            player_id: ID of the player making the move
            move_data: Dictionary containing move information

        Returns:
            Tuple of (success, error_message, updated_state)
        """
        pass

    @abstractmethod
    def check_game_over(self) -> Tuple[bool, Optional[int]]:
        """
        Check if the game is over.

        Returns:
            Tuple of (is_game_over, winner_id or None if draw)
        """
        pass

    @abstractmethod
    def get_state(self, user_id) -> Dict[str, Any]:
        """Get current game state for sending to user."""
        pass

    @abstractmethod
    def get_game_stats(self) -> Dict[str, Any]:
        """Get game stats for sending to clients."""
        pass

    def next_player(self):
        """Advance to the next player."""
        self.current_player_index = (self.current_player_index + 1) % len(self.players)

    @property
    def current_player_id(self) -> int:
        """Get current player ID."""
        return list(self.players.keys())[self.current_player_index]
