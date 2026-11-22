"""Collections API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..engine import format_enumeration
from ..models import Collection, CollectionWord, Word
from ..schemas import CollectionCreateIn

router = APIRouter(prefix="/api/collections", tags=["collections"])


@router.get("")
def list_collections(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Collection, func.count(CollectionWord.id).label("word_count"))
        .outerjoin(CollectionWord, Collection.id == CollectionWord.collection_id)
        .group_by(Collection.id)
        .order_by(Collection.id.desc())
    ).all()
    return [
        {
            "id": col.id,
            "name": col.name,
            "description": col.description,
            "language": col.language,
            "word_count": count,
            "created_at": col.created_at.isoformat() if col.created_at else None,
        }
        for col, count in rows
    ]


@router.post("", status_code=201)
def create_collection(body: CollectionCreateIn, db: Session = Depends(get_db)):
    col = Collection(name=body.name.strip(), description=body.description, language=body.language)
    db.add(col)
    db.commit()
    db.refresh(col)
    return {
        "id": col.id,
        "name": col.name,
        "description": col.description,
        "language": col.language,
        "word_count": 0,
        "created_at": col.created_at.isoformat() if col.created_at else None,
    }


@router.get("/{collection_id}")
def get_collection(
    collection_id: int,
    enumeration_display: str = Query("formatted", pattern="^(formatted|total|none)$"),
    db: Session = Depends(get_db),
):
    col = db.scalar(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(
            selectinload(Collection.word_links).selectinload(CollectionWord.word).selectinload(Word.clues)
        )
    )
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    words_out = []
    for link in col.word_links:
        w = link.word
        disp = link.display or w.display
        words_out.append(
            {
                "id": w.id,
                "position": link.position,
                "answer": w.answer,
                "display": disp,
                "raw_word": link.raw_word or disp,
                "cell_ref": link.cell_ref,
                "enumeration": format_enumeration(w.answer, disp, style=enumeration_display),
                "extra_data": link.extra_data or [],
                "language": w.language,
                "difficulty": w.difficulty,
                "clues": [
                    {
                        "id": c.id,
                        "text": c.text,
                        "difficulty": c.difficulty,
                        "source": c.source,
                        "status": c.status,
                    }
                    for c in w.clues
                ],
            }
        )

    return {
        "id": col.id,
        "name": col.name,
        "description": col.description,
        "language": col.language,
        "word_count": len(words_out),
        "words": words_out,
        "created_at": col.created_at.isoformat() if col.created_at else None,
    }


@router.delete("/{collection_id}", status_code=204)
def delete_collection(collection_id: int, db: Session = Depends(get_db)):
    col = db.get(Collection, collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    db.delete(col)
    db.commit()

