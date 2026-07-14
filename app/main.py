"""
LocalHub API의 메인 애플리케이션 모듈.
FastAPI 앱의 인스턴스를 생성하고, 미들웨어, 라우터, 수명 주기(lifespan) 이벤트 등을 설정합니다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import SessionLocal, get_settings
from app.api import router as api_router
from app.seed import create_schema, seed_if_empty
from app.services import get_rag_index


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 수명 주기 관리 (DB 생성, 초기 데이터 세딩, FAISS 빌드)."""
    with SessionLocal() as db:
        create_schema(db)
        if settings.auto_seed:
            seed_if_empty(db)
        get_rag_index().build(db)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "LocalHub API is running", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
