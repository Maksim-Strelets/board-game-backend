from starlette.websockets import WebSocketState

from fastapi import APIRouter, WebSocket, Depends, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Dict, Set
import logging

from app.database.base import get_db
from app.crud.game_room import get_game_rooms_by_game
from app.middleware.auth import require_auth
from app.schemas.game_room import GameRoomWithPlayers, GameRoomPlayerResponse
from app.schemas.user import UserResponse
from app.websockets.auth import websocket_auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(require_auth)],
)

room_list_connections: Dict[int, Set[WebSocket]] = {}


def is_websocket_connected(websocket: WebSocket) -> bool:
    """Check if websocket is still connected"""
    try:
        return websocket.client_state == WebSocketState.CONNECTED
    except Exception:
        return False


async def get_rooms_data(db: Session, game_id: int) -> list:
    """Get serialized room data for a specific game"""
    rooms = get_game_rooms_by_game(db, game_id=game_id, skip=0, limit=100)

    # Convert to list of GameRoomWithPlayers and then to dict for websocket transmission
    room_data = []
    for room in rooms:
        detailed_room = GameRoomWithPlayers(
            id=room.id,
            name=room.name,
            game_id=room.game_id,
            max_players=room.max_players,
            status=room.status,
            players=[
                GameRoomPlayerResponse(
                    room_id=room.id,
                    user_id=player.user_id,
                    id=player.id,
                    status=player.status,
                    user_data=UserResponse(
                        id=player.user.id,
                        email=player.user.email,
                        username=player.user.username,
                        is_active=player.user.is_active,
                        created_at=player.user.created_at,
                    )
                ) for player in room.players
            ]
        )
        room_data.append(detailed_room.dict())

    return room_data


@router.websocket("/ws/game/{game_id}/")
async def room_list_websocket(websocket: WebSocket, game_id: int, db: Session = Depends(get_db)):
    # Authenticate the user before accepting the connection
    user_id = await websocket_auth.authenticate(websocket)

    if not user_id:
        # Close the connection if authentication fails
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        logger.warning("WebSocket connection rejected due to authentication failure")
        return

    await websocket.accept()

    # Store the user_id with the connection for later use
    websocket.user_id = user_id

    # Add connection to room list listeners using a set to avoid duplicates
    if game_id not in room_list_connections:
        room_list_connections[game_id] = set()
    room_list_connections[game_id].add(websocket)

    try:
        # Send initial room data
        rooms_data = await get_rooms_data(db, game_id)
        await websocket.send_json({
            "type": "room_list_update",
            "rooms": jsonable_encoder(rooms_data)
        })

        # Keep connection alive until client disconnects
        while True:
            # This will raise WebSocketDisconnect when client disconnects
            data = await websocket.receive_json()
            message_type = data.get('type')
            logger.info(f"Message received from user {user_id}: {message_type}")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Always clean up the connection
        if game_id in room_list_connections:
            room_list_connections[game_id].discard(websocket)
            if not room_list_connections[game_id]:
                del room_list_connections[game_id]

async def broadcast_room_list_update(db: Session, game_id: int):
    """Broadcast room list updates to all listeners for a specific game"""
    if game_id not in room_list_connections or not room_list_connections[game_id]:
        return

    try:
        rooms_data = await get_rooms_data(db, game_id)

        # Keep track of connections to remove
        to_remove = set()

        # Broadcast to all connected clients
        for connection in room_list_connections[game_id]:
            if is_websocket_connected(connection):
                try:
                    await connection.send_json({
                        "type": "room_list_update",
                        "rooms": jsonable_encoder(rooms_data)
                    })
                except Exception as e:
                    logger.error(f"Error sending to client: {str(e)}")
                    to_remove.add(connection)
            else:
                # Connection is closed but still in our list
                to_remove.add(connection)

        # Remove dead connections
        for dead_connection in to_remove:
            room_list_connections[game_id].discard(dead_connection)

        # Clean up empty game entries
        if not room_list_connections[game_id]:
            del room_list_connections[game_id]

    except Exception as e:
        logger.error(f"Error during broadcast: {str(e)}")