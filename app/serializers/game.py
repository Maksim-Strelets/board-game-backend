from app.schemas.game_room import GameRoomPlayerResponse
from app.serializers.user import serialize_user


def serialize_player(player):
    return GameRoomPlayerResponse(
        id=player.id,
        room_id=player.room_id,
        user_id=player.user_id,
        user_data=serialize_user(player.user),
    )


def serialize_players(players: dict):
    return {_id: serialize_player(player) for _id, player in players.items()}
