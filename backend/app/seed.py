"""Bootstrap data: ``python -m app.seed``.

Creates the first owner account (password from DOJO_BOOTSTRAP_OWNER_PASSWORD) when the users
table is empty, plus the reference data a new academy needs. Safe to run repeatedly.
"""

import asyncio
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.security import hash_password
from app.models import Branch, Role, User

BRANCHES = [
    {"name": "Promenade", "code": "PRM", "address": "Hawalli"},
    {"name": "Bedaya", "code": "BDY", "address": "Sabah Al Salem"},
]


async def seed() -> None:
    s = get_settings()
    async with get_sessionmaker()() as db:
        if not await db.scalar(select(func.count()).select_from(Branch)):
            db.add_all(Branch(**b) for b in BRANCHES)

        if not await db.scalar(select(func.count()).select_from(User)):
            pw = s.bootstrap_owner_password.get_secret_value() if s.bootstrap_owner_password else ""
            if len(pw) < 10:
                sys.exit("Set DOJO_BOOTSTRAP_OWNER_PASSWORD (10+ characters) to create the owner.")
            db.add(
                User(
                    username=s.bootstrap_owner_username,
                    full_name="Academy Owner",
                    role=Role.OWNER,
                    password_hash=await hash_password(pw),
                )
            )
        await db.commit()
    await dispose_engine()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
