"""SQLAlchemy 2.x ORM models using generic types and JSON for SQLite/PostgreSQL portability."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (UniqueConstraint("answer", "language", name="uq_words_answer_language"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    answer: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    difficulty: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    clues: Mapped[list["Clue"]] = relationship(back_populates="word", cascade="all, delete-orphan")
    collection_links: Mapped[list["CollectionWord"]] = relationship(
        back_populates="word", cascade="all, delete-orphan"
    )


class Clue(Base):
    __tablename__ = "clues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # manual | import | dictionary | ai
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft"
    )  # approved | draft | needs_review | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    word: Mapped["Word"] = relationship(back_populates="clues")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled Crossword Book")
    project_type: Mapped[str] = mapped_column(String(64), nullable=False, default="crossword")
    trim_size: Mapped[str] = mapped_column(String(64), nullable=False, default="6x9")
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    import_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    chapters: Mapped[list["Collection"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Collection.chapter_index, Collection.id",
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chapter_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    project: Mapped[Optional["Project"]] = relationship(back_populates="chapters")
    word_links: Mapped[list["CollectionWord"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionWord.position",
    )


class CollectionWord(Base):
    __tablename__ = "collection_words"
    __table_args__ = (UniqueConstraint("collection_id", "word_id", name="uq_collection_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    raw_word: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_clue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cell_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extra_data: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    clue_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clues.id", ondelete="SET NULL"), nullable=True
    )

    collection: Mapped["Collection"] = relationship(back_populates="word_links")
    word: Mapped["Word"] = relationship(back_populates="collection_links")


class Puzzle(Base):
    __tablename__ = "puzzles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    clue_status: Mapped[str] = mapped_column(String(32), nullable=False, default="incomplete")
    rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grid: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    unplaced: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    entries: Mapped[list["PuzzleEntry"]] = relationship(
        back_populates="puzzle", cascade="all, delete-orphan"
    )


class PuzzleEntry(Base):
    __tablename__ = "puzzle_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    puzzle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("words.id", ondelete="SET NULL"), nullable=True
    )
    clue_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clues.id", ondelete="SET NULL"), nullable=True
    )
    answer: Mapped[str] = mapped_column(String(64), nullable=False)
    display: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(1), nullable=False)
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)

    puzzle: Mapped["Puzzle"] = relationship(back_populates="entries")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_format: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staged")
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    staged_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

