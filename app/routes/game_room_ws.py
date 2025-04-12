# app/routers/game_room_ws.py
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Dict

from app.database.base import get_db
from app.websockets.manager import connection_manager, GameWebSocketMessageType, WebSocketMessageType, WebSocketMessage
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
from app.crud.chat_message import create_chat_message
from app.schemas.chat_message import ChatMessageCreate, ChatMessageResponse
from app.serializers.user import serialize_user

from app.games.game_manager_factory import GameManagerFactory
from app.games.abstract_game import AbstractGameManager

router = APIRouter()

active_games: Dict[int, AbstractGameManager] = {}


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

    if room.status.name != RoomStatus.WAITING.name and not is_player_in_room:
        await websocket.close(code=4003, reason="Room is not available for user")
        return

    # Convert user to public schema
    user_public = serialize_user(user)

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
            user_data=serialize_user(user),
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

        if room_id in active_games:
            await active_games[room_id].resend_pending_requests(user_id)
            await active_games[room_id].resend_game_messages(user_id)

        # Create a separate task for receiving messages
        receiver_task = asyncio.create_task(
            process_websocket_messages(websocket, room_id, user_id, db)
        )

        # Wait for the receiver task to complete (when disconnected)
        await receiver_task

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Disconnect and cleanup
        connection_manager.disconnect(websocket, room_id, user_id)
        # [existing cleanup code]


async def process_websocket_messages(
        websocket: WebSocket,
        room_id: int,
        user_id: int,
        db: Session
):
    """Process incoming WebSocket messages in a separate task"""
    room = get_game_room(db, room_id)
    user = get_user(db, user_id)
    user_public = serialize_user(user)

    try:
        # Main websocket communication loop
        while True:
            data = await websocket.receive_json()

            # Handle different message types
            message_type = data.get('type')
            print("Message received", message_type)

            if message_type == WebSocketMessageType.REQUEST_RESPONSE and 'request_id' in data:
                request_id = data['request_id']

                # Find the corresponding future
                if request_id in active_games[room_id].pending_requests[user_id]:
                    future = active_games[room_id].pending_requests[user_id][request_id]
                    # Set the result to resolve the future
                    future.set_result(data)
                    continue

            elif message_type == WebSocketMessageType.CHAT:
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
                    user=serialize_user(user)
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

            elif message_type == "player_status":
                # Update player status
                new_status = data.get('status')
                room = get_game_room(db, room_id)

                if room.status.name == RoomStatus.WAITING.name and new_status in [status.value for status in PlayerStatus]:
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

                    # Initialize game when status changes to in_progress
                    if new_status == RoomStatus.IN_PROGRESS.value:
                        await start_game(db, room_id)

                    if new_status == RoomStatus.ENDED.value:
                        await end_game(db, room_id)

            elif message_type == "get_game_state":
                # Check if game is active
                if room_id in active_games:
                    game_state = active_games[room_id].get_state(user_id)
                    await websocket.send_json({
                        "type": GameWebSocketMessageType.GAME_STATE,
                        "state": jsonable_encoder(game_state),
                    })
                    if active_games[room_id].is_game_over:
                        await websocket.send_json({
                            "type": WebSocketMessageType.GAME_ENDED,
                            "state": jsonable_encoder(active_games[room_id].get_game_stats()),
                        })
                elif room.status.name == RoomStatus.IN_PROGRESS.name:
                    await start_game(db, room_id)
                else:
                    await websocket.send_json({
                        "type": GameWebSocketMessageType.GAME_ERROR,
                        "message": "Game not started"
                    })

            elif message_type == GameWebSocketMessageType.GAME_MOVE:
                # Process game move
                if room_id not in active_games:
                    await websocket.send_json({
                        "type": GameWebSocketMessageType.GAME_ERROR,
                        "message": "Game not started yet"
                    })
                    continue

                # Get the move data from the message
                move_data = data.get('move', {})

                task = asyncio.create_task(active_games[room_id].process_move(user_id, move_data))

    except Exception as e:
        print(f"WebSocket error: {e}")

    finally:
        # Disconnect and broadcast user left with user details
        connection_manager.disconnect(websocket, room_id, user_id)

        # Remove player from room
        if room.status.name == RoomStatus.WAITING.name:
            remove_player_from_room(db, room_id, user_id)

            leave_message = WebSocketMessage(
                type=WebSocketMessageType.USER_LEFT,
                user_id=user_id,
                room_id=room_id,
                user=user_public
            )
            await connection_manager.broadcast(room_id, leave_message.to_dict())

        if (
                room_id in active_games and
                active_games[room_id].is_game_over and
                not connection_manager.active_connections.get(room_id, {})
        ):
            await end_game(db, room_id)


async def start_game(db, room_id):
    # Get room data to determine players
    room = get_game_room(db, room_id)

    # Create game manager instance
    game_manager = GameManagerFactory.create_game_manager(db, room, connection_manager)

    # Store the game manager
    active_games[room_id] = game_manager

    if game_manager:
        # Initialize the game
        task = asyncio.create_task(game_manager.initialize_game())

        for player in room.players:
            new_status = PlayerStatus.IN_GAME
            updated_player = update_player_status(db, room_id, player.user_id, new_status)
            status_change_message = WebSocketMessage(
                type=WebSocketMessageType.PLAYER_STATUS_CHANGED,
                user_id=player.user_id,
                room_id=room_id,
                user=serialize_user(player.user),
                content={
                    "player": jsonable_encoder(updated_player),
                    "status": new_status
                }
            )
            await connection_manager.broadcast(room_id, status_change_message.to_dict())

        # Broadcast initial game state
        for player in room.players:
            await connection_manager.send(room_id, player.user_id, {
                "type": GameWebSocketMessageType.GAME_STATE,
                "state": jsonable_encoder(game_manager.get_state(player.user_id)),
            })
    else:
        # Game not supported
        await connection_manager.broadcast(room_id, {
            "type": GameWebSocketMessageType.GAME_ERROR,
            "message": f"Game {room.game_id} not supported"
        })


async def end_game(db, room_id):
    # Update room status to completed
    room = update_game_room(db, room_id, GameRoomUpdate(status=RoomStatus.ENDED))
    del active_games[room_id]

    # Update player statuses
    for player in room.players:
        new_status = PlayerStatus.NOT_READY
        updated_player = update_player_status(db, room_id, player.user_id, new_status)
        status_change_message = WebSocketMessage(
            type=WebSocketMessageType.PLAYER_STATUS_CHANGED,
            user_id=player.user_id,
            room_id=room_id,
            user=serialize_user(updated_player.user),
            content={
                "player": jsonable_encoder(updated_player),
                "status": new_status.value
            }
        )
        await connection_manager.broadcast(room_id, status_change_message.to_dict())