import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import require_manage_users
from app.core.security import hash_password
from app.dependencies import get_current_user, get_db
from app.models.activity_log import ActivityType
from app.models.user import User
from app.schemas.user import PasswordResetRequest, TelegramLinkToken, UserCreate, UserOut, UserUpdate
from app.services.activity_service import log_activity

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    require_manage_users(current_user)
    result = await db.execute(
        select(User).options(selectinload(User.role)).order_by(User.full_name)
    )
    return list(result.scalars().all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    require_manage_users(current_user)

    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Username '{body.username}' is already taken")

    user = User(
        full_name=body.full_name,
        username=body.username,
        password_hash=hash_password(body.password),
        role_id=body.role_id,
        telegram_handle=body.telegram_handle,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, ["role"])

    await log_activity(
        db,
        activity_type=ActivityType.USER_EDITED,
        actor_id=current_user.id,
        target_user_id=user.id,
        notes=f"User created: {user.username}",
        metadata={"action": "created", "username": user.username, "role_id": body.role_id},
        source_type="user",
        source_id=user.id,
    )

    await db.commit()
    await db.refresh(user, ["role"])
    return user


@router.get("/me/link-token", response_model=TelegramLinkToken)
async def get_telegram_link_token(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramLinkToken:
    """Generates a one-time token the user sends to the bot via /link <token>."""
    token = secrets.token_urlsafe(32)
    current_user.telegram_link_token = token
    db.add(current_user)
    await db.commit()
    return TelegramLinkToken(
        token=token,
        instructions=f"Send this command to the bot: /link {token}",
    )


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if user_id != current_user.id:
        require_manage_users(current_user)

    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.role))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    require_manage_users(current_user)

    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.role))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    changes = body.model_dump(exclude_none=True)

    # Check username uniqueness if changing
    if "username" in changes and changes["username"] != user.username:
        existing = await db.execute(
            select(User).where(User.username == changes["username"], User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, f"Username '{changes['username']}' is already taken")

    before = {k: getattr(user, k) for k in changes}
    for field, value in changes.items():
        setattr(user, field, value)
    after = {k: getattr(user, k) for k in changes}

    await log_activity(
        db,
        activity_type=ActivityType.USER_EDITED,
        actor_id=current_user.id,
        target_user_id=user.id,
        metadata={"before": before, "after": after},
        source_type="user",
        source_id=user.id,
    )

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: int,
    body: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Admin-only: set a new password for any user."""
    require_manage_users(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.password_hash = hash_password(body.new_password)

    await log_activity(
        db,
        activity_type=ActivityType.USER_PASSWORD_RESET,
        actor_id=current_user.id,
        target_user_id=user.id,
        notes=f"Password reset by {current_user.username}",
        metadata={"reset_by": current_user.username, "target_user": user.username},
        source_type="user",
        source_id=user.id,
    )

    await db.commit()
