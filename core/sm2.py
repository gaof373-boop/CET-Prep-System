"""SM-2 spaced-repetition algorithm.

Pure functions, no I/O. Trivially unit-testable.

Reference: Wozniak, P. A. (1990). Optimization of repetition spacing
in the practice of learning. Acta Neurobiologiae Experimentalis 50.

The 0-indexed list of review items a user is shown on a given day is
selected by:

  1. words where ``due_date <= today`` (overdue / due today)
  2. new words never seen yet (no ``last_seen_at``)
  3. mix 70% review / 30% new by default

The user grades each card on recall quality ``q ∈ [0, 5]``. SM-2 maps
that grade to the next interval and updates an easiness factor ``EF``.

  q < 3  → interval resets to 1 day, EF unchanged
  q >= 3 → new_interval = prev_interval * EF
  EF' = max(1.3, EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02)))

When the user reaches a high enough repetition count, the card is
considered ``mastered`` (mastered=1). SM-2 itself doesn't define a
threshold — we use ``repetitions >= 3 AND EF >= 2.5`` which is a
conservative bar (matches the "feels right" point in Anki's defaults).

Why SM-2 (not SM-17 / FSRS):
  * Industry standard, used by Anki for 20+ years.
  * Two columns (EF, interval) — trivial migration.
  * 30 lines of code — meets AC-2.1 "no speculative features".
"""
from __future__ import annotations

import datetime as _dt
import math

# SM-2 quality thresholds. Mapped from the UI's coarser signal:
#   user picked correct answer in self-test  → quality 4 (good, slight hesitation)
#   user clicked "已掌握" in detail dialog   → quality 5 (perfect recall)
#   user picked wrong answer in self-test    → quality 2 (failed, re-show tomorrow)
QUALITY_RECALL_PERFECT = 5
QUALITY_RECALL_GOOD = 4
QUALITY_RECALL_FAIL = 2

# Easiness floor — never drop below this. (SM-2 spec.)
EF_FLOOR = 1.3

# Mastery threshold — conservative. Three consecutive correct
# recalls with high easiness = "you know this".
MASTERY_REPETITIONS = 3
MASTERY_EF_THRESHOLD = 2.5


def _now() -> _dt.date:
    return _dt.date.today()


def sm2_update(
    quality: int,
    *,
    prev_ef: float = 2.5,
    prev_interval: int = 0,
    prev_repetitions: int = 0,
) -> dict:
    """Apply one SM-2 review step.

    Args:
        quality: 0..5 recall grade. <3 means "failed".
        prev_ef: previous easiness factor. Default 2.5 (new card).
        prev_interval: previous interval in days. 0 = first review.
        prev_repetitions: how many consecutive successful reviews.

    Returns
    -------
    dict with:
        ef         — new easiness factor
        interval   — new interval in days (>= 1)
        repetitions — new consecutive-correct count
        next_due   — date when this card is due again
        mastered   — bool, whether the card has crossed the mastery bar
    """
    if quality < 0 or quality > 5:
        raise ValueError(f"quality must be in 0..5, got {quality}")

    # Failed recall — reset.
    if quality < 3:
        new_repetitions = 0
        new_interval = 1
        new_ef = prev_ef  # EF unchanged on failure (SM-2 spec)
    else:
        new_repetitions = prev_repetitions + 1
        if prev_repetitions == 0:
            new_interval = 1
        elif prev_repetitions == 1:
            new_interval = 6
        else:
            new_interval = max(1, round(prev_interval * prev_ef))
        # Update EF.
        delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        new_ef = max(EF_FLOOR, prev_ef + delta)

    mastered = (
        new_repetitions >= MASTERY_REPETITIONS
        and new_ef >= MASTERY_EF_THRESHOLD
    )

    return {
        "ef": new_ef,
        "interval": new_interval,
        "repetitions": new_repetitions,
        "next_due": _now() + _dt.timedelta(days=new_interval),
        "mastered": mastered,
    }


def is_due(
    *,
    due_date: str | None,
    last_seen_at: str | None,
) -> bool:
    """Decide whether a card is due for review today.

    A card is "due" if:
      * It was never seen (``last_seen_at`` is null/empty) — counts as new
      * OR its due_date is today or in the past
    """
    if not last_seen_at:
        return True  # never seen — show it
    if not due_date:
        return True  # legacy row without due_date — show it
    try:
        due = _dt.date.fromisoformat(due_date)
    except ValueError:
        return True  # malformed — show it
    return due <= _now()


def bootstrap_from_consecutive(consecutive_correct: int) -> dict:
    """Migrate legacy data: rows that already have ``consecutive_correct
    >= 3`` are treated as mastered, with a long interval so they don't
    pop back up.

    Returns the same shape as ``sm2_update``.
    """
    if consecutive_correct >= MASTERY_REPETITIONS:
        return {
            "ef": 2.5,
            "interval": 30,  # push 30 days out
            "repetitions": consecutive_correct,
            "next_due": _now() + _dt.timedelta(days=30),
            "mastered": True,
        }
    return {
        "ef": 2.5,
        "interval": 0,
        "repetitions": consecutive_correct,
        "next_due": _now(),
        "mastered": False,
    }
