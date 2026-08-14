"""Text similarity helpers shared across memory, workforce, and lint paths."""

from __future__ import annotations

import re


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    if not set1 and not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def tokenize_words(text: str) -> set[str]:
    return {part.lower() for part in text.replace("/", " ").replace("-", " ").split() if part}


def token_jaccard(text_a: str, text_b: str) -> float:
    """Whitespace token Jaccard (skill matcher / workforce scoring)."""
    return jaccard_similarity(tokenize_words(text_a), tokenize_words(text_b))


def token_jaccard_alnum(a: str, b: str) -> float:
    """Lowercase alphanumeric token Jaccard (memory conflict detection)."""
    ta = set(re.findall(r"[a-z0-9]+", a))
    tb = set(re.findall(r"[a-z0-9]+", b))
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    if not union:
        return 0.0
    return len(inter) / len(union)
