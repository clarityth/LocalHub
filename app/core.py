from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    """애플리케이션 전역 설정."""
    app_name: str = "LocalHub"
    api_prefix: str = "/api"
    
    # DB 및 보안 설정
    database_url: str = "sqlite:///./localhub.db"
    auto_seed: bool = True
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    vector_cache_dir: str = ".cache/localhub"

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return ["*"]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    """SQLAlchemy 선언형 베이스 클래스."""

def get_db() -> Generator[Session, None, None]:
    """DB 세션 생성 및 반환."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
