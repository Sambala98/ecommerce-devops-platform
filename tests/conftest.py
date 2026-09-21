import pytest

from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

import app.cache.product_cache as product_cache_module

from app.config import get_settings
from app.db.database import Base, get_db
from app.main import app
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_interaction import ProductInteraction
from app.models.user import User, UserRole
from app.security.jwt import create_access_token
from app.security.password import hash_password


settings = get_settings()

TEST_PASSWORD = "TestPassword123!"


test_engine = create_engine(
    settings.test_database_url,
    pool_pre_ping=True,
)


TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)


test_redis_url = (
    settings.redis_url.rsplit("/", 1)[0]
    + "/1"
)


test_redis_client = Redis.from_url(
    test_redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


class UnavailableRedis:
    """
    Default Redis test double.

    Non-cache tests should not depend on a running Redis server.
    Redis operations deliberately fail so the application exercises
    its PostgreSQL fallback behavior.
    """

    def __getattr__(self, name):
        def unavailable(*args, **kwargs):
            raise RedisError(
                "Redis intentionally unavailable in this test"
            )

        return unavailable


@pytest.fixture(
    scope="session",
    autouse=True,
)
def create_test_tables():
    Base.metadata.drop_all(
        bind=test_engine,
    )

    Base.metadata.create_all(
        bind=test_engine,
    )

    yield

    Base.metadata.drop_all(
        bind=test_engine,
    )


@pytest.fixture
def database_session():
    session = TestingSessionLocal()

    try:
        yield session

    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(
    database_session,
):
    def override_get_db():
        try:
            yield database_session

        finally:
            pass

    app.dependency_overrides[
        get_db
    ] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(
    autouse=True,
)
def clean_database():
    with TestingSessionLocal() as session:
        session.execute(
            delete(ProductInteraction)
        )
        session.execute(
            delete(OrderItem)
        )
        session.execute(
            delete(Order)
        )
        session.execute(
            delete(User)
        )
        session.execute(
            delete(Product)
        )
        session.commit()

    yield

    with TestingSessionLocal() as session:
        session.execute(
            delete(ProductInteraction)
        )
        session.execute(
            delete(OrderItem)
        )
        session.execute(
            delete(Order)
        )
        session.execute(
            delete(User)
        )
        session.execute(
            delete(Product)
        )
        session.commit()


@pytest.fixture(
    autouse=True,
)
def disable_real_redis(
    monkeypatch,
):
    """
    Normal tests should not require Redis.

    Product cache code receives a Redis client that fails,
    forcing the application's graceful database fallback.
    """

    monkeypatch.setattr(
        product_cache_module,
        "redis_client",
        UnavailableRedis(),
    )


@pytest.fixture
def redis_test_client(
    monkeypatch,
):
    """
    Explicit integration fixture for tests that really test Redis.
    """

    try:
        test_redis_client.ping()

    except RedisError:
        pytest.skip(
            "Redis integration test requires a running Redis server"
        )

    monkeypatch.setattr(
        product_cache_module,
        "redis_client",
        test_redis_client,
    )

    test_redis_client.flushdb()

    yield test_redis_client

    test_redis_client.flushdb()


@pytest.fixture
def make_user(
    database_session,
):
    def _make_user(
        email: str,
        role: UserRole = UserRole.USER,
        password: str = TEST_PASSWORD,
    ) -> User:
        user = User(
            email=email,
            name="Test User",
            hashed_password=hash_password(
                password
            ),
            role=role,
        )

        database_session.add(user)
        database_session.commit()
        database_session.refresh(user)

        return user

    return _make_user


@pytest.fixture
def test_user(
    make_user,
):
    return make_user(
        email="user@example.com",
        role=UserRole.USER,
    )


@pytest.fixture
def admin_user(
    make_user,
):
    return make_user(
        email="admin@example.com",
        role=UserRole.ADMIN,
    )


@pytest.fixture
def user_headers(
    test_user,
):
    token = create_access_token(
        user_id=test_user.id,
        role=test_user.role,
    )

    return {
        "Authorization": f"Bearer {token}"
    }


@pytest.fixture
def admin_headers(
    admin_user,
):
    token = create_access_token(
        user_id=admin_user.id,
        role=admin_user.role,
    )

    return {
        "Authorization": f"Bearer {token}"
    }


@pytest.fixture
def auth_headers_for():
    def _auth_headers_for(
        user: User,
    ) -> dict[str, str]:
        token = create_access_token(
            user_id=user.id,
            role=user.role,
        )

        return {
            "Authorization": f"Bearer {token}"
        }

    return _auth_headers_for