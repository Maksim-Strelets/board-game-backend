from app.schemas.user import UserInfo


def serialize_user(user):
    return UserInfo(
        id=user.id,
        username=user.username,
    )
