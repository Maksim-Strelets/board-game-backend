from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional

from fastapi.encoders import jsonable_encoder

from app.websockets.manager import ConnectionManager, WebSocketMessageType


class AbstractGameManager(ABC):
    """Abstract base class for all game managers."""
    def __init__(self, db, room, connection_manager: ConnectionManager, game_settings: dict = None):
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

    @property
    def prev_player_id(self) -> int:
        """Get current player ID."""
        prev_player_index = (self.current_player_index - 1) % len(self.players)
        return list(self.players.keys())[prev_player_index]

    @property
    def next_player_id(self) -> int:
        """Get current player ID."""
        next_player_index = (self.current_player_index + 1) % len(self.players)
        return list(self.players.keys())[next_player_index]

    def dump(self) -> dict:
        """
        Serialize the game manager state to a dictionary for persistence.

        Returns:
            Dictionary containing the serialized game state
        """
        # Convert players dict to serializable form (player_id -> player data)
        serialized_players = {}
        for player_id, player in self.players.items():
            # Assuming player objects have a to_dict method or similar
            # If not, you'll need to create a serialization method appropriate for your player objects
            serialized_players[str(player_id)] = player.to_dict() if hasattr(player, 'to_dict') else {
                'user_id': player.user_id,
                'username': getattr(player, 'username', ''),
                # Add other relevant player attributes here
            }

        return {
            'room_id': self.room_id,
            'players': serialized_players,
            'game_state': self.game_state,
            'current_player_index': self.current_player_index,
            'is_game_over': self.is_game_over,
            'winner': self.winner,
            'game_messages': self.game_messages,
            'pending_requests': self.pending_requests,
            'sent_requests': self.sent_requests
        }

    @classmethod
    def load(cls, db, room, connection_manager: ConnectionManager, saved_state: dict) -> 'AbstractGameManager':
        """
        Create a new game manager instance from a saved state.

        Args:
            db: Database connection
            room: Room object
            connection_manager: WebSocket connection manager
            saved_state: Dictionary containing the serialized game state

        Returns:
            New game manager instance with restored state
        """
        # Create a new instance
        instance = cls(db, room, connection_manager, {})

        # Restore the game state
        instance.room_id = saved_state.get('room_id', room.id)
        instance.game_state = saved_state.get('game_state', {})
        instance.current_player_index = saved_state.get('current_player_index', 0)
        instance.is_game_over = saved_state.get('is_game_over', False)
        instance.winner = saved_state.get('winner', None)
        instance.game_messages = saved_state.get('game_messages', [])
        instance.pending_requests = saved_state.get('pending_requests', {})
        instance.sent_requests = saved_state.get('sent_requests', {})

        # The players attribute might need special handling depending on your player model
        # This is a basic implementation assuming simple player objects
        saved_players = saved_state.get('players', {})
        if saved_players and not instance.players:
            instance.players = {}
            for player_id, player_data in saved_players.items():
                # You might need to reconstruct player objects properly here
                # depending on how they're defined in your application
                player_id_int = int(player_id)
                # Find the player in the room.players list
                for player in room.players:
                    if player.user_id == player_id_int:
                        instance.players[player_id_int] = player
                        break

        return instance
