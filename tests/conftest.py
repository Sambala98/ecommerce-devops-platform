import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import delete


from app.config import get_settings
from app.db.database import Base, get_db
from app.main import app


from app.models.product import Product
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product_interaction import ProductInteraction
from app.models.user import User
from redis import Redis
import app.cache.product_cache as product_cache_module


settings = get_settings()

test_engine = create_engine(
    settings.test_database_url,
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)

test_redis_url = settings.redis_url.rsplit("/", 1)[0] + "/1"

test_redis_client = Redis.from_url(
    test_redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def database_session():
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(database_session):
    def override_get_db():
        try:
            yield database_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    
@pytest.fixture(autouse=True)
def clean_database():
    with TestingSessionLocal() as session:
        session.execute(delete(ProductInteraction))
        session.execute(delete(OrderItem))
        session.execute(delete(Order))
        session.execute(delete(User))
        session.execute(delete(Product))
        session.commit()

    yield

    with TestingSessionLocal() as session:
        session.execute(delete(ProductInteraction))
        session.execute(delete(OrderItem))
        session.execute(delete(Order))
        session.execute(delete(User))
        session.execute(delete(Product))
        session.commit()

@pytest.fixture(autouse=True)
def isolate_redis_cache(monkeypatch):
    monkeypatch.setattr(
        product_cache_module,
        "redis_client",
        test_redis_client,
    )

    test_redis_client.flushdb()

    yield

    test_redis_client.flushdb()


@pytest.fixture
def redis_test_client():
    return test_redis_client