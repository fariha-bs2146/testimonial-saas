import hashlib
import os
import secrets
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.models import User


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, key_hex = hashed_password.split("$", 1)
        key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception:
        return False


def get_or_create_default_user(session: Session) -> User:
    statement = select(User).where(User.email == "demo@example.com")
    user = session.exec(statement).first()
    if not user:
        user = User(
            email="demo@example.com",
            hashed_password=hash_password("demopassword123"),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> User:
    """
    FastAPI dependency to retrieve the current user.
    Checks headers X-User-ID or X-User-Email, falling back to the default demo user.
    Can be overridden in tests via app.dependency_overrides[get_current_user].
    """
    if x_user_id:
        try:
            user = session.get(User, int(x_user_id))
            if user:
                return user
        except ValueError:
            pass

    if x_user_email:
        statement = select(User).where(User.email == x_user_email)
        user = session.exec(statement).first()
        if user:
            return user

    return get_or_create_default_user(session)
