from __future__ import annotations

from textwrap import dedent


def d(value: str) -> str:
    return dedent(value).strip() + "\n"
