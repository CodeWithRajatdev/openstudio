"""Clue resolution, generation pipeline, alternatives/history, completeness checking, and background job runner."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...config import get_settings, redact_secrets
from ...engine.preprocess import format_enumeration
from ...models import Clue, Collection, CollectionWord, Job, Puzzle, PuzzleEntry, Word, utcnow
from .ai import AIClueRequest, AIProvider, get_ai_provider
from .dictionary import DictionaryProvider, get_dictionary_provider
from .validator import format_clue_for_render, validate_clue

USER_SOURCES = ("manual", "import")
GENERATED_SOURCES = ("dictionary", "ai")
AI_BATCH_SIZE = 20


def _pick_best_clue(clues: list[Clue], *, sources: tuple[str, ...], difficulty: Optional[str]) -> Optional[Clue]:
    candidates = [c for c in clues if c.source in sources and c.status != "rejected"]
    if not candidates:
        return None

    def _rank(c: Clue) -> tuple[int, int, float, int]:
        status_score = 2 if c.status == "approved" else (1 if c.status in ("draft", "needs_review") else 0)
        if difficulty is not None and c.difficulty == difficulty:
            diff_score = 2
        elif c.difficulty is None:
            diff_score = 1
        else:
            diff_score = 0
        ts = c.updated_at.timestamp() if c.updated_at else 0.0
        return (status_score, diff_score, ts, c.id)

    return max(candidates, key=_rank)


def resolve_clue_for_word(
    clues: list[Clue],
    *,
    mode: str = "hybrid",
    difficulty: str = "medium",
    preferred_clue_id: Optional[int] = None,
) -> Optional[Clue]:
    """Select the active clue for a word under the given mode, difficulty, and explicit selection."""
    if preferred_clue_id is not None:
        pref = next((c for c in clues if c.id == preferred_clue_id and c.status != "rejected"), None)
        if pref is not None:
            if mode == "manual" and pref.source in USER_SOURCES:
                return pref
            if mode == "automatic" and pref.source in GENERATED_SOURCES and (
                pref.difficulty == difficulty or pref.difficulty is None
            ):
                return pref
            if mode == "hybrid":
                return pref

    if mode == "manual":
        return _pick_best_clue(clues, sources=USER_SOURCES, difficulty=difficulty)

    if mode == "automatic":
        exact = [c for c in clues if c.source in GENERATED_SOURCES and c.difficulty == difficulty]
        return _pick_best_clue(exact, sources=GENERATED_SOURCES, difficulty=difficulty)

    # hybrid: prefer user clues, fall back to generated clues for this difficulty
    user_clue = _pick_best_clue(clues, sources=USER_SOURCES, difficulty=difficulty)
    if user_clue is not None:
        return user_clue
    exact = [c for c in clues if c.source in GENERATED_SOURCES and c.difficulty == difficulty]
    return _pick_best_clue(exact, sources=GENERATED_SOURCES, difficulty=difficulty)


def _clue_to_dict(c: Clue) -> dict[str, Any]:
    return {
        "id": c.id,
        "text": c.text,
        "difficulty": c.difficulty,
        "source": c.source,
        "status": c.status,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def get_collection_clues_summary(
    db: Session,
    collection_id: int,
    *,
    mode: str = "hybrid",
    difficulty: str = "medium",
    capitalization: str = "sentence",
    ending_punctuation: str = "keep",
    show_length_hint: bool = True,
    enumeration_display: str = "formatted",
) -> dict[str, Any]:
    col = db.scalar(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(
            selectinload(Collection.word_links).selectinload(CollectionWord.word).selectinload(Word.clues)
        )
    )
    if col is None:
        raise LookupError(f"Collection {collection_id} not found")

    items: list[dict[str, Any]] = []
    missing_words: list[dict[str, Any]] = []

    for link in col.word_links:
        w = link.word
        disp = link.display or w.display
        enum_str = (
            format_enumeration(w.answer, disp, style=enumeration_display)
            if show_length_hint and enumeration_display not in ("none", "off", "false")
            else ""
        )
        active = resolve_clue_for_word(
            w.clues,
            mode=mode,
            difficulty=difficulty,
            preferred_clue_id=link.clue_id,
        )
        if active is None:
            missing_words.append({"word_id": w.id, "answer": w.answer, "display": disp})
        rendered_preview = (
            format_clue_for_render(
                active.text,
                capitalization=capitalization,
                ending_punctuation=ending_punctuation,
            )
            + (f" {enum_str}" if enum_str else "")
            if active is not None
            else None
        )
        items.append(
            {
                "word_id": w.id,
                "answer": w.answer,
                "display": disp,
                "enumeration": enum_str,
                "rendered_preview": rendered_preview,
                "active_clue": _clue_to_dict(active) if active is not None else None,
                "all_clues": [
                    _clue_to_dict(c)
                    for c in sorted(
                        w.clues,
                        key=lambda x: (x.updated_at.timestamp() if x.updated_at else 0.0, x.id),
                        reverse=True,
                    )
                ],
            }
        )

    clue_status = "complete" if not missing_words and len(items) > 0 else "incomplete"
    return {
        "collection_id": col.id,
        "collection_name": col.name,
        "mode": mode,
        "difficulty": difficulty,
        "clue_status": clue_status,
        "total_words": len(items),
        "covered_words": len(items) - len(missing_words),
        "missing_words": missing_words,
        "items": items,
    }


def _collect_target_words(
    db: Session,
    *,
    collection_id: Optional[int],
    word_ids: Optional[list[int]],
) -> list[Word]:
    if collection_id is not None:
        col = db.scalar(
            select(Collection)
            .where(Collection.id == collection_id)
            .options(
                selectinload(Collection.word_links).selectinload(CollectionWord.word).selectinload(Word.clues)
            )
        )
        if col is None:
            raise LookupError(f"Collection {collection_id} not found")
        return [link.word for link in col.word_links]

    if word_ids:
        words = list(
            db.scalars(
                select(Word).where(Word.id.in_(word_ids)).options(selectinload(Word.clues))
            ).all()
        )
        return words

    return []


def create_clue_generation_job(
    db: Session,
    *,
    collection_id: Optional[int] = None,
    word_ids: Optional[list[int]] = None,
    mode: str = "hybrid",
    difficulty: str = "medium",
    regenerate: bool = False,
    verify: bool = False,
    age_group: str = "general",
) -> Job:
    words = _collect_target_words(db, collection_id=collection_id, word_ids=word_ids)
    job = Job(
        id=uuid.uuid4().hex,
        type="clue_generation",
        status="pending",
        total=len(words),
        completed=0,
        failed=0,
        payload={
            "collection_id": collection_id,
            "word_ids": [w.id for w in words],
            "mode": mode,
            "difficulty": difficulty,
            "regenerate": regenerate,
            "verify": verify,
            "age_group": age_group,
        },
        result={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def execute_clue_generation_job(
    job_id: str,
    session_factory: Callable[[], Session],
    *,
    dictionary_provider: Optional[DictionaryProvider] = None,
    ai_provider: Optional[AIProvider] = None,
) -> None:
    """Run clue generation for a Job. Dictionary clues default to needs_review; AI approved only if verified."""
    settings = get_settings()
    dict_prov = dictionary_provider or get_dictionary_provider(settings)
    ai_prov = ai_provider or get_ai_provider(settings)

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            return

        payload = job.payload or {}
        word_ids: list[int] = payload.get("word_ids", [])
        mode: str = payload.get("mode", "hybrid")
        difficulty: str = payload.get("difficulty", "medium")
        regenerate: bool = bool(payload.get("regenerate", False))
        verify: bool = bool(payload.get("verify", False))
        age_group: str = payload.get("age_group", "general")

        job.status = "running"
        db.commit()

        reused = 0
        from_dictionary = 0
        from_ai = 0
        missing: list[str] = []

        try:
            words = list(
                db.scalars(
                    select(Word).where(Word.id.in_(word_ids)).options(selectinload(Word.clues))
                ).all()
            )
            word_by_id = {w.id: w for w in words}
            ordered_words = [word_by_id[wid] for wid in word_ids if wid in word_by_id]

            ai_queue: list[tuple[Word, list[str]]] = []

            for w in ordered_words:
                if mode == "manual":
                    existing_user = _pick_best_clue(w.clues, sources=USER_SOURCES, difficulty=difficulty)
                    if existing_user is not None:
                        reused += 1
                    else:
                        job.failed += 1
                        missing.append(w.answer)
                    job.completed += 1
                    db.commit()
                    continue

                if mode == "hybrid":
                    existing_user = _pick_best_clue(w.clues, sources=USER_SOURCES, difficulty=difficulty)
                    if existing_user is not None:
                        reused += 1
                        job.completed += 1
                        db.commit()
                        continue

                if not regenerate:
                    existing_gen = [
                        c
                        for c in w.clues
                        if c.source in GENERATED_SOURCES
                        and c.difficulty == difficulty
                        and c.status in ("approved", "needs_review")
                    ]
                    if existing_gen:
                        reused += 1
                        job.completed += 1
                        db.commit()
                        continue

                # Try dictionary first -> dictionary clues ALWAYS start as needs_review
                dict_clue = dict_prov.lookup(w.display, w.answer, difficulty=difficulty)
                if dict_clue:
                    db.add(
                        Clue(
                            word_id=w.id,
                            text=dict_clue,
                            difficulty=difficulty,
                            source="dictionary",
                            status="needs_review",
                        )
                    )
                    from_dictionary += 1
                    job.completed += 1
                    db.commit()
                else:
                    hints = dict_prov.hints(w.display, w.answer, limit=3)
                    ai_queue.append((w, hints))

            # Process AI queue in batches of AI_BATCH_SIZE
            for start in range(0, len(ai_queue), AI_BATCH_SIZE):
                chunk = ai_queue[start : start + AI_BATCH_SIZE]
                reqs = [
                    AIClueRequest(answer=w.answer, display=w.display, hints=hints)
                    for w, hints in chunk
                ]
                generated_map = ai_prov.generate_batch(reqs, difficulty=difficulty, age_group=age_group)

                for w, _hints in chunk:
                    clue_text = generated_map.get(w.answer)
                    if not clue_text:
                        job.failed += 1
                        missing.append(w.answer)
                        job.completed += 1
                        continue

                    val = validate_clue(clue_text, w.answer)
                    if not val.valid:
                        job.failed += 1
                        missing.append(w.answer)
                        job.completed += 1
                        continue

                    # AI clues start approved ONLY when reverse-solve verification passes
                    status = "needs_review"
                    if verify:
                        guessed = ai_prov.verify_clue(clue_text, len(w.answer))
                        if guessed == w.answer:
                            status = "approved"

                    db.add(
                        Clue(
                            word_id=w.id,
                            text=clue_text,
                            difficulty=difficulty,
                            source="ai",
                            status=status,
                        )
                    )
                    from_ai += 1
                    job.completed += 1

                db.commit()

            job.status = "completed"
            job.result = {
                "reused": reused,
                "from_dictionary": from_dictionary,
                "from_ai": from_ai,
                "missing": missing,
            }
            db.commit()
        except Exception as exc:
            job.status = "failed"
            job.error = redact_secrets(str(exc))
            db.commit()


def regenerate_word_clue_alternatives(
    db: Session,
    word_id: int,
    *,
    difficulty: str = "medium",
    count: int = 3,
    verify: bool = False,
    age_group: str = "general",
    mode: str = "hybrid",
    dictionary_provider: Optional[DictionaryProvider] = None,
    ai_provider: Optional[AIProvider] = None,
) -> dict[str, Any]:
    """Generate 2 to 3 clue alternatives for a single word without deleting/overwriting existing clues."""
    word = db.scalar(
        select(Word).where(Word.id == word_id).options(selectinload(Word.clues))
    )
    if word is None:
        raise LookupError(f"Word {word_id} not found")

    target_count = max(2, min(3, int(count)))
    settings = get_settings()
    dict_prov = dictionary_provider or get_dictionary_provider(settings)
    ai_prov = ai_provider or get_ai_provider(settings)

    previous_clue = resolve_clue_for_word(word.clues, mode=mode, difficulty=difficulty)
    # Pin previous clue on any unpinned CollectionWord links so it remains active until user picks an alternative
    if previous_clue is not None:
        links = list(
            db.scalars(select(CollectionWord).where(CollectionWord.word_id == word.id)).all()
        )
        for lnk in links:
            if lnk.clue_id is None:
                lnk.clue_id = previous_clue.id

    existing_lower = {c.text.strip().lower() for c in word.clues}
    avoid = [c.text for c in word.clues]
    candidates: list[tuple[str, str, str]] = []  # (text, source, status)
    seen_new: set[str] = set()

    # 1. Dictionary alternatives -> always needs_review
    for d_text in dict_prov.lookup_alternatives(word.display, word.answer, difficulty=difficulty, limit=target_count):
        low = d_text.strip().lower()
        if low in existing_lower or low in seen_new:
            continue
        if validate_clue(d_text, word.answer).valid:
            candidates.append((d_text.strip(), "dictionary", "needs_review"))
            seen_new.add(low)
        if len(candidates) >= target_count:
            break

    # 2. AI alternatives if more needed
    if len(candidates) < target_count:
        hints = dict_prov.hints(word.display, word.answer, limit=3)
        req = AIClueRequest(answer=word.answer, display=word.display, hints=hints)
        ai_alts = ai_prov.generate_alternatives(
            req,
            difficulty=difficulty,
            age_group=age_group,
            count=target_count - len(candidates) + 1,
            avoid=avoid + [c[0] for c in candidates],
        )
        for a_text in ai_alts:
            low = a_text.strip().lower()
            if low in existing_lower or low in seen_new:
                continue
            if validate_clue(a_text, word.answer).valid:
                status = "needs_review"
                if verify and ai_prov.verify_clue(a_text, len(word.answer)) == word.answer:
                    status = "approved"
                candidates.append((a_text.strip(), "ai", status))
                seen_new.add(low)
            if len(candidates) >= target_count:
                break

    # 3. Offline fallback alternatives so 2-3 valid choices are always available even if AI_PROVIDER=none
    if len(candidates) < 2:
        fallback_templates = [
            f"{len(word.answer)}-letter {difficulty} crossword entry.",
            f"Word of {len(word.answer)} letters ({difficulty} puzzle).",
            f"Common {len(word.answer)}-letter term for this slot.",
        ]
        for fb_text in fallback_templates:
            low = fb_text.strip().lower()
            if low in existing_lower or low in seen_new:
                continue
            if validate_clue(fb_text, word.answer).valid:
                candidates.append((fb_text, "ai", "needs_review"))
                seen_new.add(low)
            if len(candidates) >= target_count:
                break

    created_alts: list[Clue] = []
    for text, src, stat in candidates[:target_count]:
        c = Clue(
            word_id=word.id,
            text=text,
            difficulty=difficulty,
            source=src,
            status=stat,
        )
        db.add(c)
        created_alts.append(c)

    db.commit()
    for c in created_alts:
        db.refresh(c)

    refreshed = db.scalar(
        select(Word).where(Word.id == word.id).options(selectinload(Word.clues))
    )
    assert refreshed is not None
    history = [
        _clue_to_dict(c)
        for c in sorted(
            refreshed.clues,
            key=lambda x: (x.updated_at.timestamp() if x.updated_at else 0.0, x.id),
            reverse=True,
        )
    ]
    return {
        "word_id": refreshed.id,
        "answer": refreshed.answer,
        "display": refreshed.display,
        "previous_clue": _clue_to_dict(previous_clue) if previous_clue is not None else None,
        "alternatives": [_clue_to_dict(c) for c in created_alts],
        "history": history,
    }


def select_or_restore_word_clue(
    db: Session,
    word_id: int,
    clue_id: int,
) -> dict[str, Any]:
    """Select an alternative clue or restore a historical clue as active without deleting any clue."""
    word = db.scalar(
        select(Word).where(Word.id == word_id).options(selectinload(Word.clues))
    )
    if word is None:
        raise LookupError(f"Word {word_id} not found")

    target = next((c for c in word.clues if c.id == clue_id), None)
    if target is None:
        raise LookupError(f"Clue {clue_id} not found for word {word_id}")

    target.status = "approved"
    target.updated_at = utcnow()

    for lnk in db.scalars(select(CollectionWord).where(CollectionWord.word_id == word.id)).all():
        lnk.clue_id = target.id

    affected_puzzle_ids: set[int] = set()
    for pe in db.scalars(select(PuzzleEntry).where(PuzzleEntry.word_id == word.id)).all():
        pe.clue_id = target.id
        affected_puzzle_ids.add(pe.puzzle_id)

    db.flush()
    for pid in affected_puzzle_ids:
        puz = db.scalar(select(Puzzle).where(Puzzle.id == pid).options(selectinload(Puzzle.entries)))
        if puz is not None:
            puz.clue_status = (
                "complete"
                if all(e.clue_id is not None for e in puz.entries) and len(puz.entries) > 0
                else "incomplete"
            )

    db.commit()
    refreshed = db.scalar(
        select(Word).where(Word.id == word.id).options(selectinload(Word.clues))
    )
    assert refreshed is not None
    history = [
        _clue_to_dict(c)
        for c in sorted(
            refreshed.clues,
            key=lambda x: (x.updated_at.timestamp() if x.updated_at else 0.0, x.id),
            reverse=True,
        )
    ]
    return {
        "word_id": refreshed.id,
        "answer": refreshed.answer,
        "display": refreshed.display,
        "active_clue": _clue_to_dict(target),
        "history": history,
        "all_clues": history,
    }
