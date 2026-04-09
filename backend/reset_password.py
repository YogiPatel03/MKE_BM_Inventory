import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.role import Role
from sqlalchemy import select
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"])

async def run():
    async with AsyncSessionLocal() as db:
        # Get admin role
        role = (await db.execute(select(Role).where(Role.name == "ADMIN"))).scalar_one()

        # Check if admin user exists
        user = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()

        if user:
            user.password_hash = pwd.hash("changeme123")
            print("Password updated.")
        else:
            user = User(
                full_name="Admin",
                username="admin",
                password_hash=pwd.hash("changeme123"),
                role_id=role.id,
                is_active=True,
            )
            db.add(user)
            print("Admin user created.")

        await db.commit()
        print("Done. Login with admin / changeme123")

asyncio.run(run())
