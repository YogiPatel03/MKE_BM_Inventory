import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import require_manage_users
from app.core.security import hash_password
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.user import TelegramLinkToken, UserCreate, UserOut, UserUpdate

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
    # Users can view themselves; admins can view anyone
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

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user, ["role"])
    return user
