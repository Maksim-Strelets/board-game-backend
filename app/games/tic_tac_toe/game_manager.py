# app/games/tic_tac_toe/game_manager.py
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
import time
from app.games.abstract_game import AbstractGameManager
from app.serializers.game import serialize_players


class TicTacToeManager(AbstractGameManager):
    """Implementation of Tic Tac Toe game logic."""

    def __init__(self, room):
        super().__init__(room)
        # Ensure we have exactly 2 players
        if len(room.players) != 2:
            raise ValueError("Tic Tac Toe requires exactly 2 players")

        # Symbols for players (X always goes first)
        self.symbols = {room.players[0].user_id: "X", room.players[1].user_id: "O"}

        # Add stats tracking
        self.start_time = time.time()
        self.moves_count = {player.user_id: 0 for player in room.players}
        self.player_usernames = {}  # Will be populated later

    def initialize_game(self) -> None:
        """Initialize Tic Tac Toe board and game state."""
        self.board = [None] * 9  # 3x3 board flattened to 1D array
        self.is_game_over = False
        self.winner = None
        self.current_player_index = 0  # First player starts

    def process_move(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Process a player's move."""
        # Verify it's the player's turn
        if str(player_id) != str(self.current_player_id):
            return False, "Not your turn", self.get_state(player_id)

        # Game already over
        if self.is_game_over:
            return False, "Game is already over", self.get_state(player_id)

        # Validate move data
        if 'position' not in move_data:
            return False, "Invalid move data, position required", self.get_state(player_id)

        position = move_data['position']

        # Validate position
        if not isinstance(position, int) or position < 0 or position >= 9:
            return False, "Invalid position", self.get_state(player_id)

        # Check if position is already taken
        if self.board[position] is not None:
            return False, "Position already taken", self.get_state(player_id)

        # Make the move
        self.board[position] = self.symbols[player_id]

        # Track move count
        self.moves_count[player_id] += 1

        # Check for game over
        self.is_game_over, self.winner = self.check_game_over()

        # If game not over, advance to next player
        if not self.is_game_over:
            self.next_player()

        return True, None, self.get_state(player_id)

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
                        return True, player_id

        # Check for draw (all positions filled)
        if None not in self.board:
            return True, None  # Game over with no winner (draw)

        # Game not over
        return False, None

    def get_state(self, user_id) -> Dict[str, Any]:
        """Get current game state for sending to clients."""
        return {
            "game": "tic_tac_toe",
            "board": self.board,
            "current_player": str(self.current_player_id),
            "is_game_over": self.is_game_over,
            "winner": self.winner if self.winner is not None else "draw" if self.is_game_over else None,
            "players": serialize_players(self.players),
            "symbols": self.symbols,
        }

    # Add method to get game stats
    def get_game_stats(self) -> Dict[str, Any]:
        """Get statistics about the completed game"""
        # Calculate game duration in minutes
        duration_secs = round(time.time() - self.start_time)

        # Prepare player stats
        players_stats = []
        for player in self.players.values():
            is_winner = self.winner == player.user_id if self.winner is not None else False

            players_stats.append({
                "user_id": player.user_id,
                "username": player.user.username,
                "symbol": self.symbols[player.user_id],
                "moves": self.moves_count[player.user_id],
                "is_winner": is_winner,
                "score": 1 if is_winner else 0  # Simple scoring: 1 for win, 0 otherwise
            })

        # Get winner info if there is one
        winner = None
        if self.winner is not None:
            winner = {
                "user_data": self.players.get(self.winner, f"Player {self.winner}").user,
                "symbol": self.symbols[self.winner],
            }

        return {
            "game_id": "tic_tac_toe",
            "room_id": self.room_id,
            "duration": duration_secs,
            "total_moves": sum(self.moves_count.values()),
            "winner": winner,
            "is_draw": self.is_game_over and self.winner is None,
            "players": players_stats
        }
