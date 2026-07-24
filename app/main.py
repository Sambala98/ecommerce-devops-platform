from fastapi import FastAPI

app = FastAPI(
    title="E-Commerce DevOps Platform",
    version="1.0.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "E-Commerce API is running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}