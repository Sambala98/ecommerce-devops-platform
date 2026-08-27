import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import delete


from app.config import get_settings
from app.db.database import Base, get_db
from app.main import app


from app.models.product import Product


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
def clean_products():
    with TestingSessionLocal() as session:
        session.execute(delete(Product))
        session.commit()

    yield

    with TestingSessionLocal() as session:
        session.execute(delete(Product))
        session.commit()