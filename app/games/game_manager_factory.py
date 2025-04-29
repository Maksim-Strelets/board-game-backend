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
    def create_game_manager(cls, db, room, connection_manager, game_settings) -> Optional[AbstractGameManager]:
        """
        Create a game manager instance for the specified game ID.

        Args:
            room: db game room
            connection_manager: connection_manager

        Returns:
            Game manager instance or None if game not supported
        """
        if room.game_id in cls._game_managers:
            return cls._game_managers[room.game_id](db, room, connection_manager, game_settings)

        try:
            game_names = {
                4: "tic_tac_toe",
                6: "borsht",
                7: "splendor",
                # Add more games as needed
            }

            if room.game_id not in game_names:
                return None

            game_name = game_names[room.game_id]
            module_path = f"app.games.{game_name}.game_manager"

            module = importlib.import_module(module_path)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                        issubclass(attr, AbstractGameManager) and
                        attr != AbstractGameManager):
                    cls.register_game(room.game_id, attr)

                    return attr(db, room, connection_manager, game_settings)

            return None

        except (ImportError, AttributeError) as e:
            print(f"Failed to load game manager for game ID {room.game_id}: {e}")
            return None
