from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.api.router import router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


def main():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
