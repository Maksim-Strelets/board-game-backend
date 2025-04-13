# app/games/abstract_game.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional

from fastapi.encoders import jsonable_encoder

from app.websockets.manager import ConnectionManager, WebSocketMessageType


class AbstractGameManager(ABC):
    """Abstract base class for all game managers."""

    def __init__(self, db, room, connection_manager: ConnectionManager):
        self.db = db
        self.pending_requests = {}
        self.sent_requests = {}
        self.game_messages = []
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
            "type": WebSocketMessageType.GAME_ENDED,
            "stats": jsonable_encoder(game_stats)
        })

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

    async def broadcast_game_update(self):
        for player_id in self.players.keys():
            await self.send_game_update(player_id)

    async def send_game_update(self, player_id):
        await self.connection_manager.send(self.room_id, player_id, {
            "type": "game_update",
            "state": jsonable_encoder(self.get_state(player_id))
        })

    @abstractmethod
    def check_game_over(self) -> Tuple[bool, Optional[int]]:
        """
        Check if the game is over.

        Returns:
            Tuple of (is_game_over, winner_id or None if draw)
        """
        pass

    @abstractmethod
    async def resend_pending_requests(self, user_id: int) -> None:
        """Resend pending requests to user."""
        pass

    @abstractmethod
    async def resend_game_messages(self, user_id: int) -> None:
        """Resend game messages to user."""
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
