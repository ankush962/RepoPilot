
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, ConversationMessage, User
from app.schemas import (
    ConversationCreate,
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationResponse,
    ConversationUpdate,
)
from app.services.agent import answer_question
from app.services.auth import require_user
from app.services.workspaces import (
    get_repository_for_user,
    require_permission,
)


router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def get_conversation_for_user(
    conversation_id: int,
    db: Session,
    user: User,
) -> Conversation:
    conversation = db.get(
        Conversation,
        conversation_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    repository = get_repository_for_user(
        db,
        conversation.repository_id,
        user,
    )

    if repository.workspace_id is not None:
        require_permission(
            db,
            repository.workspace_id,
            user,
            "view",
        )

    if (
        conversation.owner_username != user.username
        and repository.owner_username != user.username
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return conversation


def serialize_message(
    message: ConversationMessage,
) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
    }


def serialize_conversation(
    conversation: Conversation,
    messages: list[ConversationMessage] | None = None,
) -> dict:
    if messages is None:
        messages = []

    return {
        "id": conversation.id,
        "repository_id": conversation.repository_id,
        "owner_username": conversation.owner_username,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [
            serialize_message(message)
            for message in messages
        ],
    }


def load_conversation_messages(
    conversation_id: int,
    db: Session,
) -> list[ConversationMessage]:
    return (
        db.query(ConversationMessage)
        .filter(
            ConversationMessage.conversation_id
            == conversation_id,
        )
        .order_by(
            ConversationMessage.created_at.asc(),
            ConversationMessage.id.asc(),
        )
        .all()
    )


# ------------------------------------------------------------------
# LIST CONVERSATIONS
# ------------------------------------------------------------------

@router.get(
    "",
    response_model=list[ConversationResponse],
)
def list_conversations(
    repository_id: int = Query(
        ...,
        gt=0,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repository = get_repository_for_user(
        db,
        repository_id,
        user,
    )

    if repository.workspace_id is not None:
        require_permission(
            db,
            repository.workspace_id,
            user,
            "view",
        )

    conversations = (
        db.query(Conversation)
        .filter(
            Conversation.repository_id == repository_id,
            Conversation.owner_username == user.username,
        )
        .order_by(
            Conversation.updated_at.desc(),
        )
        .all()
    )

    return [
        serialize_conversation(
            conversation,
            load_conversation_messages(
                conversation.id,
                db,
            ),
        )
        for conversation in conversations
    ]


# ------------------------------------------------------------------
# CREATE CONVERSATION
# ------------------------------------------------------------------

@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    repository = get_repository_for_user(
        db,
        payload.repository_id,
        user,
    )

    if repository.workspace_id is not None:
        require_permission(
            db,
            repository.workspace_id,
            user,
            "view",
        )

    title = (
        payload.title.strip()
        if payload.title
        else "New conversation"
    )

    if not title:
        title = "New conversation"

    conversation = Conversation(
        repository_id=repository.id,
        owner_username=user.username,
        title=title[:255],
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return serialize_conversation(
        conversation,
        [],
    )


# ------------------------------------------------------------------
# GET CONVERSATION
# ------------------------------------------------------------------

@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    conversation = get_conversation_for_user(
        conversation_id,
        db,
        user,
    )

    messages = load_conversation_messages(
        conversation.id,
        db,
    )

    return serialize_conversation(
        conversation,
        messages,
    )


# ------------------------------------------------------------------
# UPDATE CONVERSATION
# ------------------------------------------------------------------

@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    conversation = get_conversation_for_user(
        conversation_id,
        db,
        user,
    )

    if payload.title is not None:
        title = payload.title.strip()

        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conversation title cannot be empty.",
            )

        conversation.title = title[:255]

    conversation.updated_at = datetime.datetime.utcnow()

    db.commit()
    db.refresh(conversation)

    messages = load_conversation_messages(
        conversation.id,
        db,
    )

    return serialize_conversation(
        conversation,
        messages,
    )


# ------------------------------------------------------------------
# DELETE CONVERSATION
# ------------------------------------------------------------------

@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    conversation = get_conversation_for_user(
        conversation_id,
        db,
        user,
    )

    db.delete(conversation)
    db.commit()

    return None


# ------------------------------------------------------------------
# ADD MESSAGE + AI RESPONSE
# ------------------------------------------------------------------

@router.post(
    "/{conversation_id}/messages",
    response_model=list[ConversationMessageResponse],
    status_code=status.HTTP_201_CREATED,
)
def add_conversation_message(
    conversation_id: int,
    payload: ConversationMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    conversation = get_conversation_for_user(
        conversation_id,
        db,
        user,
    )

    content = payload.content.strip()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty.",
        )

    # --------------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------------

    user_message = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )

    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # --------------------------------------------------------------
    # GENERATE AI RESPONSE
    # --------------------------------------------------------------

    try:
        answer, sources, metrics = answer_question(
            content,
            conversation.repository_id,
        )

        assistant_content = str(answer).strip()

        if not assistant_content:
            assistant_content = (
                "The indexed repository context is insufficient "
                "to determine this."
            )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate assistant response.",
        ) from exc

    # --------------------------------------------------------------
    # SAVE ASSISTANT MESSAGE
    # --------------------------------------------------------------

    assistant_message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_content,
    )

    db.add(assistant_message)

    conversation.updated_at = datetime.datetime.utcnow()

    db.commit()

    db.refresh(assistant_message)
    db.refresh(conversation)

    return [
        serialize_message(user_message),
        serialize_message(assistant_message),
    ]
