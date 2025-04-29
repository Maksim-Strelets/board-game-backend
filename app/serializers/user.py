from app.schemas.user import UserResponse


def serialize_user(user):
    return UserResponse(
        id=user.id,
        username=user.username,
    )
