"""AI clue generation providers + registry + reverse-solve verification."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from ...config import Settings
from ...engine.preprocess import normalize_answer


@dataclass
class AIClueRequest:
    answer: str
    display: str
    hints: list[str] = field(default_factory=list)


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate_batch(
        self,
        items: list[AIClueRequest],
        difficulty: str = "medium",
        age_group: str = "general",
    ) -> dict[str, str]:
        """Return mapping of normalized answer -> generated clue text."""

    @abstractmethod
    def verify_clue(self, clue: str, length: int) -> Optional[str]:
        """Reverse-solve: given clue and answer length, return normalized guessed answer or None."""

    def generate_alternatives(
        self,
        item: AIClueRequest,
        difficulty: str = "medium",
        age_group: str = "general",
        count: int = 3,
        avoid: Optional[list[str]] = None,
    ) -> list[str]:
        """Generate up to `count` distinct clue alternatives for one word."""
        single = self.generate_batch([item], difficulty=difficulty, age_group=age_group).get(item.answer)
        if not single or single in (avoid or []):
            return []
        return [single]


class NullAIProvider(AIProvider):
    name = "none"

    def generate_batch(
        self,
        items: list[AIClueRequest],
        difficulty: str = "medium",
        age_group: str = "general",
    ) -> dict[str, str]:
        return {}

    def verify_clue(self, clue: str, length: int) -> Optional[str]:
        return None


class FakeAIProvider(AIProvider):
    """Deterministic provider for offline tests."""

    name = "fake"

    def __init__(self, *, verify_succeeds: bool = True) -> None:
        self.verify_succeeds = verify_succeeds
        self._clue_to_answer: dict[str, str] = {}
        self.calls: list[list[str]] = []

    def generate_batch(
        self,
        items: list[AIClueRequest],
        difficulty: str = "medium",
        age_group: str = "general",
    ) -> dict[str, str]:
        self.calls.append([it.answer for it in items])
        out: dict[str, str] = {}
        for idx, it in enumerate(items, start=1):
            hint_note = f" ({len(it.hints)} hint)" if it.hints else ""
            clue = f"Puzzle clue #{idx} for {len(it.answer)}-letter {difficulty} {age_group} term{hint_note}."
            out[it.answer] = clue
            self._clue_to_answer[clue] = it.answer
        return out

    def generate_alternatives(
        self,
        item: AIClueRequest,
        difficulty: str = "medium",
        age_group: str = "general",
        count: int = 3,
        avoid: Optional[list[str]] = None,
    ) -> list[str]:
        avoid_set = {a.strip().lower() for a in (avoid or []) if a}
        styles = [
            f"Direct {difficulty} clue for {len(item.answer)}-letter {age_group} entry.",
            f"Alternative {difficulty} hint for a {len(item.answer)}-letter answer.",
            f"Fresh {difficulty} riddle for a {len(item.answer)}-letter solution.",
            f"Another {difficulty} angle on this {len(item.answer)}-letter entry.",
        ]
        out: list[str] = []
        for idx, text in enumerate(styles, start=1):
            if text.strip().lower() in avoid_set:
                text = f"Option {idx}: {text}"
            if text.strip().lower() in avoid_set or text in out:
                continue
            out.append(text)
            self._clue_to_answer[text] = item.answer
            if len(out) >= count:
                break
        return out

    def verify_clue(self, clue: str, length: int) -> Optional[str]:
        if not self.verify_succeeds:
            return None
        ans = self._clue_to_answer.get(clue)
        if ans and len(ans) == length:
            return ans
        return None


def _extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace:
            cleaned = brace.group(0)
    return json.loads(cleaned)


class AnthropicAIProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-5-5") -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate_batch(
        self,
        items: list[AIClueRequest],
        difficulty: str = "medium",
        age_group: str = "general",
    ) -> dict[str, str]:
        if not items:
            return {}

        difficulty_guidance = {
            "easy": "simple, direct, everyday wording",
            "medium": "standard crossword style, moderately indirect",
            "hard": "challenging, clever, less direct vocabulary (still accurate)",
        }.get(difficulty, "standard crossword style")

        payload = [
            {
                "answer": it.answer,
                "display": it.display,
                "dictionary_hints": it.hints,
            }
            for it in items
        ]

        prompt = (
            f"Write one American-style crossword clue for each word below.\n"
            f"Difficulty: {difficulty} ({difficulty_guidance}).\n"
            f"Target age group: {age_group}.\n"
            f"Rules:\n"
            f"- Never include the answer word or its stem in the clue.\n"
            f"- Keep clues concise (under 15 words), capitalized, no AI commentary.\n"
            f"- Return ONLY a JSON object mapping each exact 'answer' string to its clue string.\n\n"
            f"Words:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        msg = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        parsed = _extract_json_object(raw_text)
        return {str(k).upper(): str(v).strip() for k, v in parsed.items() if isinstance(v, str)}

    def generate_alternatives(
        self,
        item: AIClueRequest,
        difficulty: str = "medium",
        age_group: str = "general",
        count: int = 3,
        avoid: Optional[list[str]] = None,
    ) -> list[str]:
        avoid_list = list(avoid or [])
        prompt = (
            f"Write {count} distinct American-style crossword clues for the word '{item.answer}' "
            f"(display '{item.display}').\n"
            f"Difficulty: {difficulty}. Target age group: {age_group}.\n"
            f"Dictionary hints: {json.dumps(item.hints, ensure_ascii=False)}\n"
            f"Avoid repeating these existing clues: {json.dumps(avoid_list, ensure_ascii=False)}\n"
            f"Rules: never include the answer or its stem; capitalized; under 15 words.\n"
            f'Return ONLY JSON: {{"alternatives": ["clue 1", "clue 2", "clue 3"]}}'
        )
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        parsed = _extract_json_object(raw_text)
        alts = parsed.get("alternatives") or []
        out: list[str] = []
        for alt in alts:
            if isinstance(alt, str) and alt.strip() and alt.strip() not in avoid_list and alt.strip() not in out:
                out.append(alt.strip())
        return out[:count]

    def verify_clue(self, clue: str, length: int) -> Optional[str]:
        prompt = (
            f"Solve this crossword clue. The answer has exactly {length} letters (A-Z).\n"
            f"Clue: {clue}\n"
            f'Return ONLY JSON: {{"answer": "YOURGUESS"}}'
        )
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        parsed = _extract_json_object(raw_text)
        guess, _ = normalize_answer(str(parsed.get("answer", "")))
        return guess


PROVIDER_REGISTRY: dict[str, Callable[[Settings], AIProvider]] = {
    "none": lambda _s: NullAIProvider(),
    "fake": lambda _s: FakeAIProvider(),
    "anthropic": lambda s: (
        AnthropicAIProvider(api_key=s.anthropic_api_key, model=s.anthropic_model)
        if s.anthropic_api_key
        else NullAIProvider()
    ),
}


def get_ai_provider(settings: Settings) -> AIProvider:
    key = (settings.ai_provider or "anthropic").strip().lower()
    factory = PROVIDER_REGISTRY.get(key)
    if factory is None:
        return NullAIProvider()
    return factory(settings)
