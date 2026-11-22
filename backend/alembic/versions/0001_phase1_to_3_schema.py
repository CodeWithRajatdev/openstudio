"""Initial & Phase 1-3 schema migration (portable SQLite/PostgreSQL, legacy-safe).

Revision ID: 0001_phase1_to_3
Revises:
Create Date: 2026-11-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase1_to_3"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(insp: sa.Inspector, table: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))

    try:
        insp = sa.inspect(bind)
        tables = set(insp.get_table_names())

        if "words" not in tables:
            op.create_table(
                "words",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("answer", sa.String(64), nullable=False),
                sa.Column("display", sa.String(128), nullable=False),
                sa.Column("language", sa.String(16), nullable=False, server_default="en"),
                sa.Column("difficulty", sa.String(16), nullable=True),
                sa.Column("category", sa.String(128), nullable=True),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
                sa.UniqueConstraint("answer", "language", name="uq_words_answer_language"),
            )
            op.create_index("ix_words_answer", "words", ["answer"])

        if "clues" not in tables:
            op.create_table(
                "clues",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
                sa.Column("text", sa.Text(), nullable=False),
                sa.Column("difficulty", sa.String(16), nullable=True),
                sa.Column("source", sa.String(32), nullable=False),
                sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            )
            op.create_index("ix_clues_word_id", "clues", ["word_id"])

        if "projects" not in tables:
            op.create_table(
                "projects",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("name", sa.String(255), nullable=False, server_default="Untitled Crossword Book"),
                sa.Column("project_type", sa.String(64), nullable=False, server_default="crossword"),
                sa.Column("trim_size", sa.String(64), nullable=False, server_default="6x9"),
                sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
                sa.Column("settings", sa.JSON(), nullable=False),
                sa.Column("import_metadata", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            )

        if "collections" not in tables:
            op.create_table(
                "collections",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
                sa.Column("chapter_index", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("chapter_meta", sa.JSON(), nullable=False),
                sa.Column("name", sa.String(255), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("language", sa.String(16), nullable=False, server_default="en"),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            )
            op.create_index("ix_collections_project_id", "collections", ["project_id"])
        else:
            existing_cols = {c["name"] for c in insp.get_columns("collections")}
            with op.batch_alter_table("collections", recreate="never") as batch:
                if "project_id" not in existing_cols:
                    batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
                if "chapter_index" not in existing_cols:
                    batch.add_column(sa.Column("chapter_index", sa.Integer(), nullable=False, server_default="0"))
                if "chapter_meta" not in existing_cols:
                    batch.add_column(sa.Column("chapter_meta", sa.JSON(), nullable=False, server_default="{}"))
            if not _has_index(sa.inspect(bind), "collections", "ix_collections_project_id"):
                op.create_index("ix_collections_project_id", "collections", ["project_id"])

        if "collection_words" not in tables:
            op.create_table(
                "collection_words",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False),
                sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
                sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("display", sa.String(128), nullable=True),
                sa.Column("raw_word", sa.String(255), nullable=True),
                sa.Column("raw_clue", sa.Text(), nullable=True),
                sa.Column("cell_ref", sa.String(64), nullable=True),
                sa.Column("extra_data", sa.JSON(), nullable=False),
                sa.Column("clue_id", sa.Integer(), sa.ForeignKey("clues.id", ondelete="SET NULL"), nullable=True),
                sa.UniqueConstraint("collection_id", "word_id", name="uq_collection_word"),
            )
            op.create_index("ix_collection_words_collection_id", "collection_words", ["collection_id"])
            op.create_index("ix_collection_words_word_id", "collection_words", ["word_id"])
        else:
            existing_cols = {c["name"] for c in insp.get_columns("collection_words")}
            with op.batch_alter_table("collection_words", recreate="never") as batch:
                if "display" not in existing_cols:
                    batch.add_column(sa.Column("display", sa.String(128), nullable=True))
                if "raw_word" not in existing_cols:
                    batch.add_column(sa.Column("raw_word", sa.String(255), nullable=True))
                if "raw_clue" not in existing_cols:
                    batch.add_column(sa.Column("raw_clue", sa.Text(), nullable=True))
                if "cell_ref" not in existing_cols:
                    batch.add_column(sa.Column("cell_ref", sa.String(64), nullable=True))
                if "extra_data" not in existing_cols:
                    batch.add_column(sa.Column("extra_data", sa.JSON(), nullable=False, server_default="[]"))
                if "clue_id" not in existing_cols:
                    batch.add_column(sa.Column("clue_id", sa.Integer(), nullable=True))

        if "puzzles" not in tables:
            op.create_table(
                "puzzles",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.id", ondelete="SET NULL"), nullable=True),
                sa.Column("title", sa.String(255), nullable=False, server_default=""),
                sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
                sa.Column("clue_status", sa.String(32), nullable=False, server_default="incomplete"),
                sa.Column("rows", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("cols", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("grid", sa.JSON(), nullable=False),
                sa.Column("settings", sa.JSON(), nullable=False),
                sa.Column("validation", sa.JSON(), nullable=False),
                sa.Column("unplaced", sa.JSON(), nullable=False),
                sa.Column("stats", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            )
            op.create_index("ix_puzzles_collection_id", "puzzles", ["collection_id"])

        if "puzzle_entries" not in tables:
            op.create_table(
                "puzzle_entries",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("puzzle_id", sa.Integer(), sa.ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False),
                sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id", ondelete="SET NULL"), nullable=True),
                sa.Column("clue_id", sa.Integer(), sa.ForeignKey("clues.id", ondelete="SET NULL"), nullable=True),
                sa.Column("answer", sa.String(64), nullable=False),
                sa.Column("display", sa.String(128), nullable=True),
                sa.Column("number", sa.Integer(), nullable=False),
                sa.Column("direction", sa.String(1), nullable=False),
                sa.Column("row", sa.Integer(), nullable=False),
                sa.Column("col", sa.Integer(), nullable=False),
                sa.Column("length", sa.Integer(), nullable=False),
            )
            op.create_index("ix_puzzle_entries_puzzle_id", "puzzle_entries", ["puzzle_id"])
        else:
            existing_cols = {c["name"] for c in insp.get_columns("puzzle_entries")}
            with op.batch_alter_table("puzzle_entries", recreate="never") as batch:
                if "display" not in existing_cols:
                    batch.add_column(sa.Column("display", sa.String(128), nullable=True))

        if "jobs" not in tables:
            op.create_table(
                "jobs",
                sa.Column("id", sa.String(64), primary_key=True),
                sa.Column("type", sa.String(64), nullable=False),
                sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
                sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("payload", sa.JSON(), nullable=False),
                sa.Column("result", sa.JSON(), nullable=False),
                sa.Column("error", sa.Text(), nullable=True),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            )
            op.create_index("ix_jobs_type", "jobs", ["type"])

        if "import_batches" not in tables:
            op.create_table(
                "import_batches",
                sa.Column("id", sa.String(64), primary_key=True),
                sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
                sa.Column("filename", sa.String(255), nullable=True),
                sa.Column("source_format", sa.String(32), nullable=False),
                sa.Column("status", sa.String(32), nullable=False, server_default="staged"),
                sa.Column("report", sa.JSON(), nullable=False),
                sa.Column("staged_data", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            )
            op.create_index("ix_import_batches_project_id", "import_batches", ["project_id"])
        else:
            existing_cols = {c["name"] for c in insp.get_columns("import_batches")}
            with op.batch_alter_table("import_batches", recreate="never") as batch:
                if "project_id" not in existing_cols:
                    batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
            if not _has_index(sa.inspect(bind), "import_batches", "ix_import_batches_project_id"):
                op.create_index("ix_import_batches_project_id", "import_batches", ["project_id"])
    finally:
        if is_sqlite:
            bind.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    # Destructive downgrade omitted to preserve user puzzle data.
    pass
