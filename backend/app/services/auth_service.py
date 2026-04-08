from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import verify_password
from app.models.user import User


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    """
    Verifies username and password. Returns the User on success, None on failure.
    Always runs verify_password even if user not found to prevent timing attacks.
    """
    result = await db.execute(
        select(User)
        .where(User.username == username.lower(), User.is_active == True)
        .options(selectinload(User.role))
    )
    user = result.scalar_one_or_none()

    if not user:
        # Prevent timing attack — still run bcrypt against a valid dummy hash
        verify_password("dummy", "$2b$12$ta2IJu3t9nqK2x/klWoMk.nOE1vVi6OpDfNxoZ8dmIeyc7OB4WYBi")
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
