from sqlalchemy.orm import Session, joinedload
from app.database.models import ChatMessage, User
from app.schemas.chat_message import ChatMessageCreate


def create_chat_message(db: Session, chat_message: ChatMessageCreate) -> ChatMessage:
    """
    Create a new chat message in the database
    """
    db_message = ChatMessage(
        room_id=chat_message.room_id,
        user_id=chat_message.user_id,
        content=chat_message.content
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


def get_room_chat_messages(db: Session, room_id: int, limit: int = 50) -> list[ChatMessage]:
    """
    Retrieve recent chat messages for a specific room
    """
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.room_id == room_id)
        .options(joinedload(ChatMessage.user))
        .order_by(ChatMessage.timestamp.asc())
        .limit(limit)
        .all()
    )


def delete_room_chat_messages(db: Session, room_id: int):
    """
    Delete all chat messages for a specific room
    """
    db.query(ChatMessage).filter(ChatMessage.room_id == room_id).delete()
    db.commit()
