"""Phase 6 hardening migration: idempotent foreign-key performance indexes.

Revision ID: 0002_phase6_hardening
Revises: 0001_phase1_to_3
Create Date: 2026-11-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase6_hardening"
down_revision: Union[str, Sequence[str], None] = "0001_phase1_to_3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_SPECS: tuple[tuple[str, str, list[str]], ...] = (
    ("words", "ix_words_answer", ["answer"]),
    ("clues", "ix_clues_word_id", ["word_id"]),
    ("collections", "ix_collections_project_id", ["project_id"]),
    ("collection_words", "ix_collection_words_collection_id", ["collection_id"]),
    ("collection_words", "ix_collection_words_word_id", ["word_id"]),
    ("puzzles", "ix_puzzles_collection_id", ["collection_id"]),
    ("puzzle_entries", "ix_puzzle_entries_puzzle_id", ["puzzle_id"]),
    ("jobs", "ix_jobs_type", ["type"]),
    ("import_batches", "ix_import_batches_project_id", ["project_id"]),
)


def _has_index(insp: sa.Inspector, table: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    for table, index_name, columns in _INDEX_SPECS:
        if table in tables and not _has_index(insp, table, index_name):
            op.create_index(index_name, table, columns)
            insp = sa.inspect(bind)


def downgrade() -> None:
    # Non-destructive downgrade to keep existing query performance & data intact.
    pass
