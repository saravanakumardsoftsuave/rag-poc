from collections.abc import Generator
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import settings

engine = create_engine(settings.postgres_url, pool_pre_ping=True)


class ChatLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    question: str
    answer: str
    source_documents: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    chunk_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def has_ingested_documents() -> bool:
    with Session(engine) as session:
        return session.exec(select(DocumentRecord.id).limit(1)).first() is not None
