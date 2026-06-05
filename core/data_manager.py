"""Data access layer for the CET prep system.

Provides high-level CRUD methods over the SQLite database. UI code should
only depend on this module — never on raw ``sqlite3``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from .db_init import DB_PATH


class DataManager:
    """Thin wrapper around the SQLite database used by all views."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        if not self.db_path.exists():
            from . import db_init
            db_init.init_database()

    # ---------- connection helpers ----------
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    # ---------- vocabulary ----------
    def list_vocabulary(
        self,
        level: str,
        *,
        min_star: int = 1,
        exact_star: int | None = None,
        search: str | None = None,
        order_by: str = "star_rating DESC, frequency DESC",
    ) -> list[dict[str, Any]]:
        """Fetch vocabulary rows for ``level``.

        Filtering rules:
        - ``min_star`` (default 1) is a *floor* — only rows with
          ``star_rating >= min_star`` are returned.
        - ``exact_star`` (optional) — when set, restricts to rows with
          ``star_rating = exact_star`` exactly. Overrides ``min_star``.
        - ``search`` (optional) — case-insensitive substring match on
          word or translation.

        Each row is enriched with a ``translation_fallback`` key: the
        in-code dictionary's value if the DB translation is empty, so
        the UI never has to deal with blank Chinese.
        """
        from .translations import lookup_translation

        if exact_star is not None:
            sql = (
                "SELECT * FROM vocabulary "
                "WHERE level = ? AND star_rating = ?"
            )
            params: list[Any] = [level, exact_star]
        else:
            sql = (
                "SELECT * FROM vocabulary "
                "WHERE level = ? AND star_rating >= ?"
            )
            params = [level, min_star]

        if search:
            sql += " AND (word LIKE ? OR translation LIKE ?)"
            kw = f"%{search}%"
            params.extend([kw, kw])
        sql += f" ORDER BY {order_by}"
        with self._conn() as c:
            rows = self._rows_to_dicts(c.execute(sql, params).fetchall())

        # Inject a fallback translation so the UI never shows blank
        # Chinese for known words.
        for row in rows:
            tr = (row.get("translation") or "").strip()
            if not tr:
                fb = lookup_translation(row.get("word") or "")
                if fb:
                    row["translation_fallback"] = fb
                else:
                    row["translation_fallback"] = None
            else:
                row["translation_fallback"] = None
        return rows

    def star_distribution(self, level: str) -> dict[int, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT star_rating, COUNT(*) AS n FROM vocabulary "
                "WHERE level = ? GROUP BY star_rating ORDER BY star_rating",
                (level,),
            ).fetchall()
        return {r["star_rating"]: r["n"] for r in rows}

    def count_missing_translations(self, level: str | None = None) -> int:
        """Count vocabulary rows with an empty translation column.

        Used by the online-translation backfill script to know how much
        work is left.
        """
        with self._conn() as c:
            if level:
                row = c.execute(
                    "SELECT COUNT(*) FROM vocabulary "
                    "WHERE level = ? AND (translation IS NULL OR translation = '')",
                    (level,),
                ).fetchone()
            else:
                row = c.execute(
                    "SELECT COUNT(*) FROM vocabulary "
                    "WHERE translation IS NULL OR translation = ''"
                ).fetchone()
        return int(row[0])

    def list_words_missing_translation(
        self,
        *,
        level: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return rows whose ``translation`` column is empty.

        Limited to ``limit`` rows so the backfill tool can be run
        incrementally without overwhelming the network.
        """
        with self._conn() as c:
            if level:
                rows = c.execute(
                    "SELECT id, level, word FROM vocabulary "
                    "WHERE level = ? AND (translation IS NULL OR translation = '') "
                    "ORDER BY id LIMIT ?",
                    (level, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, level, word FROM vocabulary "
                    "WHERE translation IS NULL OR translation = '' "
                    "ORDER BY id LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def update_vocabulary_translation(self, word_id: int, translation: str) -> bool:
        """Write a freshly-fetched translation back to the database.

        Returns True if the row was updated, False if the new value
        was empty (we never overwrite a row with blank data).
        """
        if not translation or not translation.strip():
            return False
        translation = translation.strip()[:200]
        with self._conn() as c:
            cur = c.execute(
                "UPDATE vocabulary SET translation = ? WHERE id = ? "
                "AND (translation IS NULL OR translation = '')",
                (translation, word_id),
            )
            c.commit()
            return cur.rowcount > 0

    def upsert_vocabulary_row(
        self,
        *,
        level: str,
        word: str,
        phonetic: str = "",
        pos: str = "",
        translation: str = "",
        frequency: int = 50,
        star_rating: int = 3,
        example_sentence: str = "",
        example_translation: str = "",
        tags: str = "",
    ) -> int | None:
        """Insert a new vocabulary row. If the (level, word) already
        exists, do nothing (return None) so re-runs are safe.

        Returns the new row id, or None if it was a duplicate.
        """
        if not word or not word.strip():
            return None
        word = word.strip().lower()
        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM vocabulary WHERE level = ? AND word = ?",
                (level, word),
            ).fetchone()
            if existing:
                return None
            cur = c.execute(
                "INSERT INTO vocabulary "
                "(level, word, phonetic, pos, translation, frequency, star_rating, "
                " example_sentence, example_translation, tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    level, word, phonetic[:80], pos[:30], translation[:200],
                    frequency, star_rating, example_sentence[:300],
                    example_translation[:200], tags[:120],
                ),
            )
            c.commit()
            return int(cur.lastrowid)

    # ---------- writing ----------
    def list_writing(self, level: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            return self._rows_to_dicts(
                c.execute(
                    "SELECT * FROM writing WHERE level = ? "
                    "ORDER BY year DESC, id DESC",
                    (level,),
                ).fetchall()
            )

    def list_predictions(self, level: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            return self._rows_to_dicts(
                c.execute(
                    "SELECT * FROM writing_predictions WHERE level = ? "
                    "ORDER BY confidence DESC",
                    (level,),
                ).fetchall()
            )

    # ---------- reading / listening / translation ----------
    def _list_section(self, table: str, level: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            return self._rows_to_dicts(
                c.execute(
                    f"SELECT * FROM {table} WHERE level = ? "
                    "ORDER BY year DESC, id DESC",
                    (level,),
                ).fetchall()
            )

    def list_reading(self, level: str) -> list[dict[str, Any]]:
        return self._list_section("reading", level)

    def list_listening(self, level: str) -> list[dict[str, Any]]:
        return self._list_section("listening", level)

    def list_translation(self, level: str) -> list[dict[str, Any]]:
        return self._list_section("translation", level)

    # ---------- generated practice ----------
    def save_generated_practice(
        self,
        *,
        section: str,
        level: str,
        parent_id: int,
        title: str,
        content: str,
        answers: str,
        analysis: str,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO generated_practice "
                "(parent_id, section, level, title, content, answers, analysis) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (parent_id, section, level, title, content, answers, analysis),
            )
            c.commit()
            return cur.lastrowid

    def list_generated(self, section: str, level: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            return self._rows_to_dicts(
                c.execute(
                    "SELECT * FROM generated_practice "
                    "WHERE section = ? AND level = ? "
                    "ORDER BY created_at DESC, id DESC",
                    (section, level),
                ).fetchall()
            )

    # ---------- stats ----------
    def section_stats(self, level: str) -> dict[str, int]:
        stats: dict[str, int] = {}
        for table, label in [
            ("vocabulary", "vocab"),
            ("writing", "writing"),
            ("reading", "reading"),
            ("listening", "listening"),
            ("translation", "translation"),
        ]:
            with self._conn() as c:
                cur = c.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE level = ?", (level,)
                )
                stats[label] = cur.fetchone()[0]
        return stats

    # ================================================================
    # Memory / quiz / wrong-book system
    # ================================================================
    def set_mastered(self, word_id: int, mastered: bool) -> bool:
        """Toggle the per-word ``mastered`` flag. Returns the new state."""
        with self._conn() as c:
            c.execute(
                "UPDATE vocabulary SET mastered = ? WHERE id = ?",
                (1 if mastered else 0, word_id),
            )
            c.commit()
        return mastered

    def toggle_mastered(self, word_id: int) -> bool:
        """Flip the ``mastered`` flag. Returns the new state."""
        with self._conn() as c:
            row = c.execute(
                "SELECT mastered FROM vocabulary WHERE id = ?", (word_id,),
            ).fetchone()
            if not row:
                return False
            new_val = 0 if row["mastered"] else 1
            c.execute(
                "UPDATE vocabulary SET mastered = ? WHERE id = ?",
                (new_val, word_id),
            )
            c.commit()
        return bool(new_val)

    def record_wrong(self, word_id: int) -> int:
        """Bump ``wrong_count`` and reset ``consec_correct`` to 0.
        Returns the new wrong_count."""
        with self._conn() as c:
            c.execute(
                "UPDATE vocabulary "
                "SET wrong_count = wrong_count + 1, "
                "    consec_correct = 0, "
                "    last_seen_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (word_id,),
            )
            row = c.execute(
                "SELECT wrong_count FROM vocabulary WHERE id = ?", (word_id,),
            ).fetchone()
            c.commit()
        return int(row["wrong_count"]) if row else 0

    def record_correct(self, word_id: int) -> tuple[int, bool]:
        """Bump ``consec_correct``; if it reaches 2, also drop
        ``wrong_count`` to 0 (the spec: "连续正确答对 2 次自动移出错题本").
        Returns (new_consec_correct, was_removed_from_wrong_book)."""
        was_removed = False
        with self._conn() as c:
            c.execute(
                "UPDATE vocabulary "
                "SET consec_correct = consec_correct + 1, "
                "    last_seen_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (word_id,),
            )
            row = c.execute(
                "SELECT consec_correct, wrong_count FROM vocabulary WHERE id = ?",
                (word_id,),
            ).fetchone()
            if row and row["consec_correct"] >= 2 and row["wrong_count"] > 0:
                c.execute(
                    "UPDATE vocabulary "
                    "SET wrong_count = 0, consec_correct = 0 WHERE id = ?",
                    (word_id,),
                )
                was_removed = True
            row = c.execute(
                "SELECT consec_correct, wrong_count FROM vocabulary WHERE id = ?",
                (word_id,),
            ).fetchone()
            c.commit()
        consec = int(row["consec_correct"]) if row else 0
        return consec, was_removed

    def list_mastered(self, level: str, *, limit: int = 2000) -> list[dict[str, Any]]:
        """Words the user has checked the '已掌握' box on."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM vocabulary "
                "WHERE level = ? AND mastered = 1 "
                "ORDER BY last_seen_at DESC, word ASC LIMIT ?",
                (level, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_wrong_book(self, level: str, *, limit: int = 2000) -> list[dict[str, Any]]:
        """Words the user has gotten wrong at least once.
        Sorted by wrong_count DESC then last_seen_at DESC."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM vocabulary "
                "WHERE level = ? AND wrong_count > 0 "
                "ORDER BY wrong_count DESC, last_seen_at DESC LIMIT ?",
                (level, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_mastered(self, level: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM vocabulary "
                "WHERE level = ? AND mastered = 1",
                (level,),
            ).fetchone()
        return int(row["n"])

    def count_wrong(self, level: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM vocabulary "
                "WHERE level = ? AND wrong_count > 0",
                (level,),
            ).fetchone()
        return int(row["n"])

    def get_word_by_id(self, word_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM vocabulary WHERE id = ?", (word_id,),
            ).fetchone()
        return dict(row) if row else None

    # ================================================================
    # V2.0 Dashboard + cross-module flow
    # ================================================================
    def dashboard_stats(self, level: str | None = None) -> dict[str, int]:
        """Aggregate everything the home dashboard needs in a few
        SQL round-trips.

        Args:
            level:  None → counts across both CET-4 and CET-6
                    "CET4" / "CET6" → restrict
        Returns a dict with keys:
            mastered      — vocab rows with mastered=1
            total_words   — all vocab rows
            wrong_book    — vocab rows with wrong_count > 0
            practice_reading — reading rows (proxy for "已练习阅读")
            practice_listening — listening rows (proxy for "已播放听力")
            ai_essay_grades    — rows in generated_practice for writing
            ai_trans_grades    — rows in generated_practice for translation
        """
        levels = ["CET4", "CET6"] if level is None else [level]
        out = {
            "mastered": 0, "total_words": 0, "wrong_book": 0,
            "practice_reading": 0, "practice_listening": 0,
            "ai_essay_grades": 0, "ai_trans_grades": 0,
        }
        with self._conn() as c:
            placeholders = ",".join("?" * len(levels))
            out["total_words"] = c.execute(
                f"SELECT COUNT(*) AS n FROM vocabulary "
                f"WHERE level IN ({placeholders})", levels,
            ).fetchone()["n"]
            out["mastered"] = c.execute(
                f"SELECT COUNT(*) AS n FROM vocabulary "
                f"WHERE level IN ({placeholders}) AND mastered = 1", levels,
            ).fetchone()["n"]
            out["wrong_book"] = c.execute(
                f"SELECT COUNT(*) AS n FROM vocabulary "
                f"WHERE level IN ({placeholders}) AND wrong_count > 0", levels,
            ).fetchone()["n"]
            for sec in ("reading", "listening"):
                out[f"practice_{sec}"] = c.execute(
                    f"SELECT COUNT(*) AS n FROM {sec} "
                    f"WHERE level IN ({placeholders})", levels,
                ).fetchone()["n"]
            out["ai_essay_grades"] = c.execute(
                "SELECT COUNT(*) AS n FROM generated_practice "
                "WHERE section = 'writing'",
            ).fetchone()["n"]
            out["ai_trans_grades"] = c.execute(
                "SELECT COUNT(*) AS n FROM generated_practice "
                "WHERE section = 'translation'",
            ).fetchone()["n"]
        return out

    def add_word_to_wrong_book(
        self,
        word: str,
        *,
        level: str = "CET4",
        translation: str = "",
        source: str = "writing/translation catch",
    ) -> tuple[int, bool]:
        """Insert a new vocabulary row OR bump its wrong_count.

        Behaviour:
            - If a row exists for (level, word) AND already has a
              translation, we just +1 to wrong_count and zero out
              consec_correct.
            - If the row has no translation yet, we set the user-supplied
              translation instead of overwriting an existing one.
            - If the row doesn't exist, insert a new one with star_rating=2
              and wrong_count=1.

        Returns (row_id, created_new).
        """
        word = (word or "").strip().lower()
        if not word:
            return (0, False)
        with self._conn() as c:
            row = c.execute(
                "SELECT id, translation, wrong_count, consec_correct "
                "FROM vocabulary WHERE level = ? AND word = ?",
                (level, word),
            ).fetchone()
            if row:
                existing_trans = row["translation"] or ""
                new_trans = translation if (translation and not existing_trans) else existing_trans
                c.execute(
                    "UPDATE vocabulary "
                    "SET wrong_count = wrong_count + 1, "
                    "    consec_correct = 0, "
                    "    translation = ?, "
                    "    last_seen_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (new_trans, row["id"]),
                )
                c.commit()
                return (int(row["id"]), False)
            cur = c.execute(
                "INSERT INTO vocabulary "
                "(level, word, phonetic, pos, translation, frequency, "
                " star_rating, example_sentence, example_translation, "
                " tags, mastered, wrong_count, consec_correct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    level, word, "[/]", "",
                    translation.strip()[:200] or "(暂无中文释义)",
                    50, 2, "", "",
                    f"catch:{source}",
                    0, 1, 0,
                ),
            )
            c.commit()
            return (int(cur.lastrowid), True)

    def save_ai_catch_log(
        self,
        *,
        section: str,
        level: str,
        word: str,
        source_id: int,
    ) -> int:
        """Record that the user added ``word`` to the wrong book from
        ``section`` (writing/translation). Returns the new log id."""
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO generated_practice "
                "(parent_id, section, level, title, content, answers, analysis) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_id, section, level,
                 f"[错词捕捉] {word}",
                 f"From {section} catch: {word}",
                 "n/a", f"auto-caught from {section}"),
            )
            c.commit()
            return int(cur.lastrowid)


    # ================================================================
    # Writing / Reading / Translation bulk-upsert (for the
    # 灌装脚本). Idempotent: if (level, year, session, title-ish) row
    # exists, skip; else insert.
    # ================================================================
    def upsert_writing(
        self,
        *,
        level: str,
        year: int,
        session: str,
        title: str = "",
        topic: str = "",
        requirements: str = "",
        sample_essay: str = "",
        key_phrases: str = "",
        category: str = "",
        highlights: str = "",
    ) -> int | None:
        """Insert a writing row; returns the new id or None on duplicate.

        Dedup key: (level, year, session, topic) — if all four match an
        existing row, skip. ``title`` falls back to ``topic`` for the
        key when ``title`` is empty.
        """
        dedup_topic = (topic or title or "").strip()[:200]
        if not dedup_topic:
            return None
        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM writing "
                "WHERE level = ? AND year = ? AND session = ? "
                "  AND (topic = ? OR (topic IS NULL AND ? = ''))",
                (level, year, session, dedup_topic, dedup_topic),
            ).fetchone()
            if existing:
                return None
            cur = c.execute(
                "INSERT INTO writing "
                "(level, exam_type, year, session, title, topic, "
                " requirements, sample_essay, key_phrases, category, highlights) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    level, level, year, session,
                    title or topic, dedup_topic,
                    requirements, sample_essay, key_phrases, category,
                    highlights,
                ),
            )
            c.commit()
            return int(cur.lastrowid)

    def upsert_reading(
        self,
        *,
        level: str,
        year: int,
        session: str,
        passage_title: str = "",
        passage: str = "",
        questions: str = "",
        answers: str = "",
        analysis: str = "",
        topic_type: str = "",
        options: str = "",
        answer: str = "",
    ) -> int | None:
        """Insert a reading row; dedup on (level, year, session, title)."""
        dedup_title = passage_title.strip()[:200]
        if not dedup_title:
            return None
        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM reading "
                "WHERE level = ? AND year = ? AND session = ? "
                "  AND (passage_title = ? OR (passage_title IS NULL AND ? = ''))",
                (level, year, session, dedup_title, dedup_title),
            ).fetchone()
            if existing:
                return None
            cur = c.execute(
                "INSERT INTO reading "
                "(level, exam_type, year, session, passage_title, passage, "
                " questions, answers, analysis, topic_type, options, answer) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    level, level, year, session,
                    dedup_title, passage, questions, answers, analysis,
                    topic_type, options, answer,
                ),
            )
            c.commit()
            return int(cur.lastrowid)

    def upsert_translation(
        self,
        *,
        level: str,
        year: int,
        session: str,
        chinese_text: str = "",
        english_reference: str = "",
        english_translation: str = "",
        key_points: str = "",
        key_terms: str = "",
        analysis: str = "",
        topic_type: str = "",
    ) -> int | None:
        """Insert a translation row; dedup on
        (level, year, session, chinese_text-prefix-100)."""
        zh = (chinese_text or "").strip()[:100]
        if not zh:
            return None
        en = english_translation or english_reference
        kp = key_terms or key_points
        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM translation "
                "WHERE level = ? AND year = ? AND session = ? "
                "  AND substr(chinese_text, 1, 100) = ?",
                (level, year, session, zh),
            ).fetchone()
            if existing:
                return None
            cur = c.execute(
                "INSERT INTO translation "
                "(level, exam_type, year, session, chinese_text, "
                " english_reference, english_translation, key_points, key_terms, "
                " analysis, topic_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    level, level, year, session, chinese_text,
                    en, en, kp, kp, analysis, topic_type,
                ),
            )
            c.commit()
            return int(cur.lastrowid)

    def count_writing(self, level: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM writing WHERE level = ?", (level,),
            ).fetchone()
        return int(row["n"])

    def count_reading(self, level: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM reading WHERE level = ?", (level,),
            ).fetchone()
        return int(row["n"])

    def count_translation(self, level: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM translation WHERE level = ?", (level,),
            ).fetchone()
        return int(row["n"])


if __name__ == "__main__":
    dm = DataManager()
    print("CET4 vocab (top 5 by star):")
    for r in dm.list_vocabulary("CET4")[:5]:
        print(f"  {r['word']:<14} {r['star_rating']}★  freq={r['frequency']}  {r['translation']}")
    print("CET4 writing count:", len(dm.list_writing("CET4")))
    print("CET4 reading count:", len(dm.list_reading("CET4")))
    print("CET6 stats:", dm.section_stats("CET6"))
