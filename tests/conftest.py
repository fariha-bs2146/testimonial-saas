from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.database import get_session
from app.main import app
from app.models import User
from app.services.auth_service import get_current_user, hash_password


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="free_user")
def free_user_fixture(session: Session) -> User:
    user = User(
        email="freeuser@example.com",
        hashed_password=hash_password("freepassword123"),
        stripe_customer_id=None,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="pro_user")
def pro_user_fixture(session: Session) -> User:
    user = User(
        email="prouser@example.com",
        hashed_password=hash_password("propassword123"),
        stripe_customer_id="cus_test_pro_123",
    )
    # Set internal pro indicator for testing without live Stripe API
    user._is_pro = True
    session.add(user)
    session.commit()
    session.refresh(user)
    user._is_pro = True
    return user


@pytest.fixture(name="client")
def client_fixture(session: Session, free_user: User) -> Generator[TestClient, None, None]:
    def get_session_override():
        return session

    def get_current_user_override():
        return free_user

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_current_user_override

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(name="pro_client")
def pro_client_fixture(session: Session, pro_user: User) -> Generator[TestClient, None, None]:
    def get_session_override():
        return session

    def get_current_user_override():
        return pro_user

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_current_user_override

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
