from fastapi import FastAPI

from app.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)


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