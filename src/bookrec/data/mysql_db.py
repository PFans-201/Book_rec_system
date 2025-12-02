from __future__ import annotations

from datetime import datetime
from typing import Generator

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, create_engine, Index, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from bookrec.config import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):
    """MySQL: Core user identity and demographics (structured, transactional)."""
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_category: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    gender: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ratings: Mapped[list["Rating"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Book(Base):
    """MySQL: Core book metadata (structured, reference data)."""
    __tablename__ = "books"

    isbn: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(255))
    year: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str | None] = mapped_column(String(255))

    ratings: Mapped[list["Rating"]] = relationship(back_populates="book", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_books_author", "author"),
        Index("idx_books_title", "title"),
    )


class Rating(Base):
    """MySQL: Transactional rating events (structured, append-only log)."""
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    isbn: Mapped[str] = mapped_column(ForeignKey("books.isbn", ondelete="CASCADE"), index=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="ratings")
    book: Mapped[Book] = relationship(back_populates="ratings")

    __table_args__ = (
        Index("ux_user_item", "user_id", "isbn", unique=True),
        Index("idx_rating_value", "rating"),
    )


_engine = None
_SessionLocal = None


def get_mysql_engine():
    """Get SQLAlchemy engine for MySQL."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # mysql+mysqlconnector://user:password@host:port/database
        url = (
            f"mysql+mysqlconnector://{settings.mysql_user}:{settings.mysql_password}"
            f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
        )
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_mysql_engine(), class_=Session, expire_on_commit=False)
    return _SessionLocal


def init_mysql_db(drop_existing: bool = False) -> None:
    """Create MySQL tables."""
    engine = get_mysql_engine()
    if drop_existing:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def session_scope() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
