"""Unified vector primitives in points (top-left origin, +x right, +y down)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass(frozen=True)
class RectPrimitive:
    x: float
    y: float
    width: float
    height: float
    fill: Optional[str] = None
    stroke: Optional[str] = None
    stroke_width: float = 0.0


@dataclass(frozen=True)
class LinePrimitive:
    x1: float
    y1: float
    x2: float
    y2: float
    stroke: str = "#000000"
    stroke_width: float = 1.0


@dataclass(frozen=True)
class TextPrimitive:
    x: float
    y: float  # baseline y in points (top-left origin)
    text: str
    font_size: float = 10.0
    font_family: str = "Vera"
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    anchor: str = "start"  # "start" | "middle" | "end"


Primitive = Union[RectPrimitive, LinePrimitive, TextPrimitive]


@dataclass
class PagePrimitives:
    width_pt: float
    height_pt: float
    primitives: list[Primitive] = field(default_factory=list)
    bookmark: Optional[str] = None
    is_blank: bool = False
