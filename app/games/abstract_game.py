# app/games/abstract_game.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, Optional


class AbstractGameManager(ABC):
    """Abstract base class for all game managers."""

    def __init__(self, room_id: int, players: List[int]):
        self.room_id = room_id
        self.player_ids = players
        self.game_state = {}
        self.current_player_index = 0
        self.is_game_over = False
        self.winner = None

    @abstractmethod
    def initialize_game(self) -> Dict[str, Any]:
        """Initialize game state and return initial state."""
        pass

    @abstractmethod
    def process_move(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
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
    def get_state(self) -> Dict[str, Any]:
        """Get current game state for sending to clients."""
        pass

    def next_player(self):
        """Advance to the next player."""
        self.current_player_index = (self.current_player_index + 1) % len(self.player_ids)

    @property
    def current_player_id(self) -> int:
        """Get current player ID."""
        return self.player_ids[self.current_player_index]