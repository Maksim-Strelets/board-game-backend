# app/routers/game_room_ws.py
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from app.database.base import get_db
from app.websockets.manager import connection_manager
from app.crud.game_room import (
    get_game_room,
    add_player_to_room,
    get_room_player,
    update_player_status,
    remove_player_from_room,
    update_game_room,
)
from app.crud.user import get_user  # Assuming you have a user CRUD module
from app.schemas.game_room import (
    RoomStatus,
    PlayerStatus,
    GameRoomPlayerResponse,
    GameRoomUpdate,
)
from app.schemas.user import UserResponse  # Assuming you have a user schema
from app.crud.chat_message import create_chat_message
from app.schemas.chat_message import ChatMessageCreate, ChatMessageResponse

router = APIRouter()


class WebSocketMessageType:
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    CHAT = "chat"
    GAME_ACTION = "game_action"
    ROOM_STATUS_CHANGED = "room_status_changed"
    PLAYER_STATUS_CHANGED = "player_status_changed"


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


@router.websocket("/ws/game/{game_id}/room/{room_id}")
async def websocket_room_endpoint(
        websocket: WebSocket,
        game_id: int,
        room_id: int,
        db: Session = Depends(get_db)
):
    # Validate room exists and belongs to the game
    room = get_game_room(db, room_id)
    if not room or room.game_id != game_id:
        await websocket.close(code=4004, reason="Room not found")
        return

    # Extract user_id from query params (in a real app, this would come from authentication)
    try:
        user_id = int(websocket.query_params.get('user_id', 0))
    except (ValueError, TypeError):
        await websocket.close(code=4003, reason="Invalid user ID")
        return

    # Fetch user data
    user = get_user(db, user_id)
    if not user:
        await websocket.close(code=4003, reason="User not found")
        return

    is_player_in_room = user_id in [player.user_id for player in room.players]

    if room.status != RoomStatus.WAITING and not is_player_in_room:
        await websocket.close(code=4003, reason="Room is not available for user")
        return

    # Convert user to public schema
    user_public = UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        created_at=user.created_at,
    )

    try:

        # Add player to room
        if not is_player_in_room:
            player_data = add_player_to_room(db, room_id, user_id)
        else:
            player_data = get_room_player(db, room_id, user_id)

        # Convert player data to schema
        player_response = GameRoomPlayerResponse(
            id=player_data.id,
            room_id=player_data.room_id,
            user_id=player_data.user_id,
            status=player_data.status,
            user_data=UserResponse(
                id=player_data.user.id,
                email=player_data.user.email,
                username=player_data.user.username,
                is_active=player_data.user.is_active,
                created_at=player_data.user.created_at,
            ),
        )

        # Connect to websocket
        await connection_manager.connect(websocket, room_id, user_id)

        # Broadcast user joined with user details
        if not is_player_in_room:
            join_message = WebSocketMessage(
                type=WebSocketMessageType.USER_JOINED,
                user_id=user_id,
                room_id=room_id,
                user=user_public,
                content={
                    "player": jsonable_encoder(player_response)
                }
            )
            await connection_manager.broadcast(room_id, join_message.to_dict())

        # Main websocket communication loop
        while True:
            data = await websocket.receive_json()

            # Handle different message types
            message_type = data.get('type')

            if message_type == WebSocketMessageType.CHAT:
                # Validate message content
                message_content = data.get('message', '').strip()
                if not message_content:
                    continue

                # Create chat message in database
                chat_message_create = ChatMessageCreate(
                    room_id=room_id,
                    user_id=user_id,
                    content=message_content
                )
                db_message = create_chat_message(db, chat_message_create)

                # Convert to response schema
                chat_message_response = ChatMessageResponse(
                    id=db_message.id,
                    room_id=db_message.room_id,
                    user_id=db_message.user_id,
                    content=db_message.content,
                    timestamp=db_message.timestamp,
                    user=UserResponse(
                        id=user.id,
                        email=user.email,
                        username=user.username,
                        is_active=user.is_active,
                        created_at=user.created_at
                    )
                )

                # Broadcast chat message with full details
                chat_message_ws = WebSocketMessage(
                    type=WebSocketMessageType.CHAT,
                    user_id=user_id,
                    room_id=room_id,
                    user=user_public,
                    content={
                        "message": jsonable_encoder(chat_message_response)
                    }
                )
                await connection_manager.broadcast(room_id, chat_message_ws.to_dict())

            elif message_type == WebSocketMessageType.GAME_ACTION:
                # Broadcast game-specific actions with user details
                game_action_message = WebSocketMessage(
                    type=WebSocketMessageType.GAME_ACTION,
                    user_id=user_id,
                    room_id=room_id,
                    user=user_public,
                    content={
                        "action": data.get('action'),
                        "payload": data.get('payload')
                    }
                )
                await connection_manager.broadcast(room_id, game_action_message.to_dict())

            elif message_type == "room_status":
                # Update room status (only if authorized)
                new_status = data.get('status')
                update_game_room(db, room_id, GameRoomUpdate(status=RoomStatus(new_status)))
                if new_status in [status.value for status in RoomStatus]:
                    # In a real app, add authorization check
                    status_message = WebSocketMessage(
                        type=WebSocketMessageType.ROOM_STATUS_CHANGED,
                        user_id=user_id,
                        room_id=room_id,
                        user=user_public,
                        content={
                            "status": new_status
                        }
                    )
                    await connection_manager.broadcast(room_id, status_message.to_dict())

            elif message_type == "player_status":
                # Update player status
                new_status = data.get('status')
                if new_status in [status.value for status in PlayerStatus]:
                    # Update player status in the database
                    updated_player = update_player_status(
                        db,
                        room_id,
                        user_id,
                        PlayerStatus(new_status)
                    )

                    # Prepare status change message
                    status_change_message = WebSocketMessage(
                        type=WebSocketMessageType.PLAYER_STATUS_CHANGED,
                        user_id=user_id,
                        room_id=room_id,
                        user=user_public,
                        content={
                            "player": jsonable_encoder(updated_player),
                            "status": new_status
                        }
                    )
                    await connection_manager.broadcast(room_id, status_change_message.to_dict())

    except Exception as e:
        print(f"WebSocket error: {e}")

    finally:
        # Disconnect and broadcast user left with user details
        connection_manager.disconnect(websocket, room_id, user_id)

        # Remove player from room
        if room.status == RoomStatus.WAITING:
            remove_player_from_room(db, room_id, user_id)

            leave_message = WebSocketMessage(
                type=WebSocketMessageType.USER_LEFT,
                user_id=user_id,
                room_id=room_id,
                user=user_public
            )
            await connection_manager.broadcast(room_id, leave_message.to_dict())