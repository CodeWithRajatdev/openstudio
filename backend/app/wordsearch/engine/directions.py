"""The eight word-search directions as (d_row, d_col) steps.

Convention: row 0 is the top, col 0 is the left.
"Forward" directions are the four a reader naturally scans
(L->R, T->B, and both downward diagonals); "reverse" are their opposites.
"""
from __future__ import annotations

DIRECTIONS: dict[str, tuple[int, int]] = {
    "E": (0, 1),    # horizontal left -> right
    "W": (0, -1),   # horizontal right -> left   (reverse)
    "S": (1, 0),    # vertical top -> bottom
    "N": (-1, 0),   # vertical bottom -> top     (reverse)
    "SE": (1, 1),   # diagonal top-left -> bottom-right
    "NW": (-1, -1), # diagonal bottom-right -> top-left (reverse)
    "SW": (1, -1),  # diagonal top-right -> bottom-left
    "NE": (-1, 1),  # diagonal bottom-left -> top-right (reverse)
}

HORIZONTAL = ("E", "W")
VERTICAL = ("S", "N")
DIAGONAL = ("SE", "NW", "SW", "NE")
REVERSE = ("W", "N", "NW", "NE")


def allowed_directions(
    horizontal: bool, vertical: bool, diagonal: bool, reverse: bool
) -> list[str]:
    """Directions enabled by the category switches.

    A direction is allowed when its category is on AND (it is a forward
    direction OR reverse placement is on).
    """
    names: list[str] = []
    for enabled, group in (
        (horizontal, HORIZONTAL),
        (vertical, VERTICAL),
        (diagonal, DIAGONAL),
    ):
        if not enabled:
            continue
        for d in group:
            if d in REVERSE and not reverse:
                continue
            names.append(d)
    return names
