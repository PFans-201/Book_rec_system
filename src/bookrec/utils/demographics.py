"""
Demographic utilities: age bucketing and deterministic random gender.
"""
from __future__ import annotations

from typing import Optional
import math
import random


def age_to_category(age: Optional[float | int]) -> str:
    """Bucket an age into a coarse category.

    Categories:
    - child (< 12)
    - juvenile (12-17)
    - young-adult (18-29)
    - 30-40 (30-39)
    - 40-60 (40-59)
    - 60+ (>= 60)
    - unknown (missing or invalid)
    """
    if age is None:
        return "unknown"
    try:
        a = float(age)
        if math.isnan(a):
            return "unknown"
    except Exception:
        return "unknown"

    if a < 12:
        return "child"
    if a < 18:
        return "juvenile"
    if a < 30:
        return "young-adult"
    if a < 40:
        return "30-40"
    if a < 60:
        return "40-60"
    return "60+"


def assign_gender(user_id: int, allow_nonbinary: bool = True) -> str:
    """Assign a deterministic pseudo-random gender label based on user_id.

    Deterministic: seeded by user_id so results are reproducible across runs.
    Set allow_nonbinary=True to include a third option with lower probability.
    """
    rng = random.Random(user_id)
    if allow_nonbinary:
        # 40% male, 40% female, 20% non-binary (tweakable)
        r = rng.random()
        if r < 0.40:
            return "male"
        if r < 0.80:
            return "female"
        return "non-binary"
    else:
        return rng.choice(["male", "female"])