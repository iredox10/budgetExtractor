from __future__ import annotations

import re


def normalize_label(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = re.sub(r"\s*-\s*$", "", cleaned)
    cleaned = cleaned.strip(" .:")
    return cleaned
