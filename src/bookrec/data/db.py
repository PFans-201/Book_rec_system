from __future__ import annotations

from dataclasses import dataclass
from typing import Generator

from sqlalchemy import Column, Float, ForeignKey, Integer, String, create_engine, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from bookrec.config import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    ratings: Mapped[list["Rating"]] = relationship(back_populates="user")


class Book(Base):
    __tablename__ = "books"

    isbn: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(255))
    year: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str | None] = mapped_column(String(255))

    ratings: Mapped[list["Rating"]] = relationship(back_populates="book")

    __table_args__ = (
        Index("idx_books_author", "author"),
        Index("idx_books_title", "title"),
    )


class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    isbn: Mapped[str] = mapped_column(ForeignKey("books.isbn", ondelete="CASCADE"), index=True)
    rating: Mapped[float] = mapped_column(Float)

    user: Mapped[User] = relationship(back_populates="ratings")
    book: Mapped[Book] = relationship(back_populates="ratings")

    __table_args__ = (
        Index("ux_user_item", "user_id", "isbn", unique=True),
        Index("idx_rating_value", "rating"),
    )


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.db_url, echo=False, future=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)
    return _SessionLocal


def init_db(drop_existing: bool = False) -> None:
    engine = get_engine()
    if drop_existing:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@dataclass
class SessionContext:
    session: Session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> None:
        self.session.close()


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
