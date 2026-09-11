from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.routers.products import router as products_router
from app.routers.users import router as users_router
from app.routers.orders import router as orders_router
from app.routers.interactions import router as interactions_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

app.include_router(products_router)
app.include_router(users_router)
app.include_router(orders_router)
app.include_router(interactions_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "E-Commerce API is running",
        "environment": settings.app_environment,
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "environment": settings.app_environment,
    }


@app.get("/health/database")
def database_health_check(
    database_session: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        database_session.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from error