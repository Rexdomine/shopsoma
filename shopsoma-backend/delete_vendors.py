"""Delete existing vendor users so they can be recreated with profiles"""
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.user import User, UserRole


async def delete_vendors():
    async with async_session_maker() as session:
        # Delete vendor users
        stmt = delete(User).where(User.role == UserRole.VENDOR)
        result = await session.execute(stmt)
        await session.commit()

        print(f"Deleted {result.rowcount} vendor users")


if __name__ == "__main__":
    asyncio.run(delete_vendors())
