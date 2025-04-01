# app/websockets/manager.py
from typing import Dict, Set, Any
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Mapping of room_id to active websocket connections
        self.active_connections: Dict[int, dict[int, WebSocket]] = {}
        # Mapping of user_id to their current room
        self.user_rooms: Dict[int, int] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):
        """Connect a user to a specific room's websocket"""
        await websocket.accept()

        # Add to room connections
        if room_id not in self.active_connections:
            self.active_connections[room_id] = dict()
        self.active_connections[room_id][user_id] = websocket

        # Track user's current room
        self.user_rooms[user_id] = room_id

    def disconnect(self, websocket: WebSocket, room_id: int, user_id: int):
        """Disconnect a user from a room"""
        if user_id in self.active_connections.get(room_id, dict()):
            del self.active_connections[room_id][user_id]

            # Remove user from user_rooms if they were in this room
            if self.user_rooms.get(user_id) == room_id:
                del self.user_rooms[user_id]

    async def broadcast(self, room_id: int, message: Dict[str, Any]):
        """Broadcast a message to all connections in a room"""
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id].values():
                await connection.send_json(message)

    async def send(self, room_id: int, user_id: int, message: Dict[str, Any]):
        if user_id in self.active_connections.get(room_id, dict()):
            await self.active_connections[room_id][user_id].send_json(message)

    def get_room_connections(self, room_id: int) -> Set[WebSocket]:
        """Get all connections for a specific room"""
        return self.active_connections.get(room_id, set())

    def get_user_room(self, user_id: int) -> int:
        """Get the room a user is currently in"""
        return self.user_rooms.get(user_id)


# Create a singleton instance
connection_manager = ConnectionManager()