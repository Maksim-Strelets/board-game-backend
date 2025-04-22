from typing import Dict, Set, Any, Optional
from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from starlette import status

from app.schemas.user import UserResponse
from app.websockets.auth import websocket_auth


class ConnectionManager:
    def __init__(self):
        # Mapping of room_id to active websocket connections
        self.active_connections: Dict[int, dict[int, WebSocket]] = {}
        # Mapping of user_id to their current room
        self.user_rooms: Dict[int, int] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):
        """Connect a user to a specific room's websocket"""
        # Authenticate the user before accepting the connection
        user_id = await websocket_auth.authenticate(websocket)

        if not user_id:
            # Close the connection if authentication fails
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
            return
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

    def get_room_connections(self, room_id: int) -> dict[int, WebSocket]:
        """Get all connections for a specific room"""
        return self.active_connections.get(room_id, dict())

    def get_user_room(self, user_id: int) -> int:
        """Get the room a user is currently in"""
        return self.user_rooms.get(user_id)


# Create a singleton instance
connection_manager = ConnectionManager()


class GameWebSocketMessageType:
    GAME_STATE = "game_state"
    GAME_UPDATE = "game_update"
    GAME_MOVE = "game_move"
    GAME_ERROR = "game_error"
    RESEND_PENDING_DATA = "resend_pending_data"


class WebSocketMessageType:
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    CHAT = "chat"
    GAME_ACTION = "game_action"
    REQUEST_RESPONSE = "request_response"
    ROOM_STATUS_CHANGED = "room_status_changed"
    PLAYER_STATUS_CHANGED = "player_status_changed"
    GAME_ENDED = "game_ended"


class WebSocketMessage:
    def __init__(
            self,
            type: str,
            user_id: int,
            room_id: int,
            user: Optional[UserResponse] = None,
            content: Optional[Dict[str, Any]] = None
    ):
        self.type = type
        self.user_id = user_id
        self.room_id = room_id
        self.user = user
        self.content = content or {}

    def to_dict(self):
        """
        Convert the message to a dictionary for WebSocket transmission
        """
        message_dict = {
            "type": self.type,
            "user_id": self.user_id,
            "room_id": self.room_id,
        }

        # Add user data if available
        if self.user:
            message_dict["user"] = jsonable_encoder(self.user)

        # Merge content
        message_dict.update(self.content)

        return message_dict
