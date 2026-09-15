"""Filterable mistake chips stored as a comma-separated Trade.mistake_tags string."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

# Keys must stay stable; labels can change in config.MISTAKE_CHIP_CHOICES.
DEFAULT_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("early_exit", "Early exit"),
    ("moved_stop", "Moved stop"),
    ("no_sl", "No stop loss"),
    ("off_playbook", "Off playbook"),
    ("news_fade", "News fade"),
    ("size_too_big", "Size too big"),
)


def allowed_keys(choices: Sequence[Tuple[str, str]] | None = None) -> frozenset:
    rows = choices if choices is not None else DEFAULT_CHOICES
    return frozenset(str(k) for k, _ in rows if k)


def parse_mistake_tags(raw: str | None) -> List[str]:
    if not raw:
        return []
    seen = set()
    out: List[str] = []
    for part in str(raw).split(","):
        key = part.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def serialize_mistake_tags(keys: Iterable[str], *, choices: Sequence[Tuple[str, str]] | None = None) -> str | None:
    allow = allowed_keys(choices)
    seen = set()
    out: List[str] = []
    for key in keys:
        k = str(key or "").strip()
        if not k or k not in allow or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return ",".join(out) if out else None


def mistake_label_map(choices: Sequence[Tuple[str, str]] | None = None) -> dict:
    rows = choices if choices is not None else DEFAULT_CHOICES
    return {str(k): str(label) for k, label in rows}


def labels_for(raw: str | None, *, choices: Sequence[Tuple[str, str]] | None = None) -> List[str]:
    mapping = mistake_label_map(choices)
    return [mapping.get(k, k) for k in parse_mistake_tags(raw)]
