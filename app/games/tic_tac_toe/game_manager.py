# app/games/tic_tac_toe/game_manager.py
from typing import Dict, Any, Tuple, List, Optional
from app.games.abstract_game import AbstractGameManager


class TicTacToeManager(AbstractGameManager):
    """Implementation of Tic Tac Toe game logic."""

    def __init__(self, room_id: int, players: List[int]):
        super().__init__(room_id, players)
        # Ensure we have exactly 2 players
        if len(players) != 2:
            raise ValueError("Tic Tac Toe requires exactly 2 players")

        # Symbols for players (X always goes first)
        self.symbols = {str(players[0]): "X", str(players[1]): "O"}

    def initialize_game(self) -> Dict[str, Any]:
        """Initialize Tic Tac Toe board and game state."""
        self.board = [None] * 9  # 3x3 board flattened to 1D array
        self.is_game_over = False
        self.winner = None
        self.current_player_index = 0  # First player starts

        return self.get_state()

    def process_move(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Process a player's move."""
        # Verify it's the player's turn
        if str(player_id) != str(self.current_player_id):
            return False, "Not your turn", self.get_state()

        # Game already over
        if self.is_game_over:
            return False, "Game is already over", self.get_state()

        # Validate move data
        if 'position' not in move_data:
            return False, "Invalid move data, position required", self.get_state()

        position = move_data['position']

        # Validate position
        if not isinstance(position, int) or position < 0 or position >= 9:
            return False, "Invalid position", self.get_state()

        # Check if position is already taken
        if self.board[position] is not None:
            return False, "Position already taken", self.get_state()

        # Make the move
        self.board[position] = self.symbols[str(player_id)]

        # Check for game over
        self.is_game_over, self.winner = self.check_game_over()

        # If game not over, advance to next player
        if not self.is_game_over:
            self.next_player()

        return True, None, self.get_state()

    def check_game_over(self) -> Tuple[bool, Optional[int]]:
        """Check if the game is over (win or draw)."""
        # Win patterns: rows, columns, diagonals
        patterns = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # rows
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # columns
            [0, 4, 8], [2, 4, 6]  # diagonals
        ]

        # Check for win
        for pattern in patterns:
            if (self.board[pattern[0]] is not None and
                    self.board[pattern[0]] == self.board[pattern[1]] == self.board[pattern[2]]):
                # Find winning player
                winning_symbol = self.board[pattern[0]]
                for player_id, symbol in self.symbols.items():
                    if symbol == winning_symbol:
                        return True, int(player_id)

        # Check for draw (all positions filled)
        if None not in self.board:
            return True, None  # Game over with no winner (draw)

        # Game not over
        return False, None

    def get_state(self) -> Dict[str, Any]:
        """Get current game state for sending to clients."""
        return {
            "game": "tic_tac_toe",
            "board": self.board,
            "current_player": str(self.current_player_id),
            "is_game_over": self.is_game_over,
            "winner": str(self.winner) if self.winner is not None else "draw" if self.is_game_over else None,
            "players": self.symbols
        }