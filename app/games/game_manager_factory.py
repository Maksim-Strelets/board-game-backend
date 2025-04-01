# app/games/game_manager_factory.py
from typing import Dict, List, Optional, Type
import importlib
from app.games.abstract_game import AbstractGameManager


class GameManagerFactory:
    """Factory for creating game manager instances based on game ID."""

    # Registry of game managers
    _game_managers: Dict[int, Type[AbstractGameManager]] = {}

    @classmethod
    def register_game(cls, game_id: int, manager_class: Type[AbstractGameManager]):
        """Register a game manager class for a specific game ID."""
        cls._game_managers[game_id] = manager_class

    @classmethod
    def create_game_manager(cls, room) -> Optional[AbstractGameManager]:
        """
        Create a game manager instance for the specified game ID.

        Args:
            room: db game room

        Returns:
            Game manager instance or None if game not supported
        """
        # Check if we have already registered this game
        if room.game_id in cls._game_managers:
            return cls._game_managers[room.game_id](room)

        # Try to dynamically load the game module
        try:
            # Determine the expected module path based on game_id
            # This assumes you have a directory structure like:
            # app/games/{game_name}/game_manager.py

            # First, query the database to get the game name from game_id
            # For this example, we'll use a hardcoded mapping
            game_names = {
                4: "tic_tac_toe",
                # Add more games as needed
            }

            if room.game_id not in game_names:
                return None

            game_name = game_names[room.game_id]
            module_path = f"app.games.{game_name}.game_manager"

            # Import the module
            module = importlib.import_module(module_path)

            # Find the game manager class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                # Check if it's a class and a subclass of AbstractGameManager
                if (isinstance(attr, type) and
                        issubclass(attr, AbstractGameManager) and
                        attr != AbstractGameManager):
                    # Register the game manager for future use
                    cls.register_game(room.game_id, attr)

                    # Create and return an instance
                    return attr(room)

            return None

        except (ImportError, AttributeError) as e:
            print(f"Failed to load game manager for game ID {room.game_id}: {e}")
            return None