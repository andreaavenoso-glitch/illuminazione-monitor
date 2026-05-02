"""Bootstrap an admin user from BOOTSTRAP_ADMIN_EMAIL/PASSWORD env vars.

Idempotent. Run once on first deploy::

    docker compose exec api python -m infra.scripts.seed_admin

If the user already exists, only the password is reset (use as
"reset admin password" tool too).
"""
from __future__ import annotations

import asyncio
import os
import sys

from app.auth.security import hash_password
from app.core.database import SessionLocal
from app.repositories.user_repository import UserRepository


async def main() -> int:
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        print(
            "ERROR: set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in the env "
            "before running this script.",
            file=sys.stderr,
        )
        return 1
    if len(password) < 12:
        print("ERROR: BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters.", file=sys.stderr)
        return 2

    async with SessionLocal() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(email)
        if existing:
            await repo.update(
                existing,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
            await session.commit()
            print(f"updated existing user {email} -> role=admin, password reset")
        else:
            await repo.create(
                email=email,
                password_hash=hash_password(password),
                role="admin",
                full_name="Bootstrap Admin",
            )
            await session.commit()
            print(f"created admin user {email}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
