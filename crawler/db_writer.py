"""Persist ``RawItem`` instances into the CET prep database.

Reuses the schema in ``core.db_init`` and normalizes a few common
shapes (vocab, reading, listening, translation, writing) into the
matching table.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
from pathlib import Path
from typing import Iterable

from core.db_init import DB_PATH
from crawler.base import RawItem, log


class DBWriter:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        # ensure DB schema exists
        from core import db_init
        db_init.init_database()
        self._inserted = 0
        self._skipped = 0
        self._seen_keys: set[tuple[str, str, str]] = set()  # (section, level, key)
        # Pre-load existing keys to avoid duplicates on re-runs
        with self._conn() as c:
            for table, key_col in [
                ("vocabulary", "word"), ("writing", "topic"),
                ("reading", "passage_title"), ("listening", "audio_script"),
                ("translation", "chinese_text"),
            ]:
                for level, key in c.execute(
                    f"SELECT level, {key_col} FROM {table}"
                ).fetchall():
                    self._seen_keys.add((table, level or "shared", (key or "").strip()[:200]))

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    # ---------- helpers ----------
    @staticmethod
    def _fingerprint(*parts: str) -> str:
        h = hashlib.md5("|".join((p or "").strip() for p in parts).encode("utf-8"))
        return h.hexdigest()[:12]

    def _is_new(self, section: str, level: str, key: str) -> bool:
        norm = (section, level or "shared", (key or "").strip()[:200])
        if not norm[2]:
            return True
        if norm in self._seen_keys:
            return False
        self._seen_keys.add(norm)
        return True

    # ---------- write ----------
    def write(self, item: RawItem) -> bool:
        sec = item.section
        if sec == "vocabulary":
            return self._write_vocab(item)
        if sec == "reading":
            return self._write_reading(item)
        if sec == "listening":
            return self._write_listening(item)
        if sec == "translation":
            return self._write_translation(item)
        if sec == "writing":
            return self._write_writing(item)
        log.warning(f"  unknown section: {sec}")
        return False

    def _write_vocab(self, item: RawItem) -> bool:
        p = item.payload
        word = (p.get("word") or "").strip().lower()
        if not word:
            self._skipped += 1
            return False
        # Wiktionary enrichment: if the word already exists for this level,
        # UPDATE it with the new fields instead of inserting a duplicate.
        if item.source == "wiktionary":
            return self._enrich_vocab(item, word)
        # New word path
        if not self._is_new("vocabulary", item.level, word):
            self._skipped += 1
            return False
        # Pseudo star rating based on word length.
        word_len = len(word)
        star = max(1, min(5, 6 - (word_len // 4)))
        freq = random.randint(20, 200) if star >= 3 else random.randint(1, 30)
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO vocabulary "
                    "(level, word, phonetic, pos, translation, frequency, star_rating, "
                    " example_sentence, example_translation, tags) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.level, word,
                        p.get("phonetic", ""), p.get("pos", ""),
                        p.get("translation", ""), freq, star,
                        p.get("example_sentence", ""),
                        p.get("example_translation", ""),
                        f"crawler:{item.source}",
                    ),
                )
                c.commit()
        except sqlite3.IntegrityError as e:
            log.warning(f"  vocab insert conflict {word}: {e}")
            self._skipped += 1
            return False
        self._inserted += 1
        return True

    def _enrich_vocab(self, item: RawItem, word: str) -> bool:
        """Update existing vocab row with Wiktionary data, ignoring rows
        where the new fields are empty.
        """
        p = item.payload
        with self._conn() as c:
            row = c.execute(
                "SELECT id, phonetic, translation, example_sentence "
                "FROM vocabulary WHERE level = ? AND word = ? "
                "ORDER BY id LIMIT 1",
                (item.level, word),
            ).fetchone()
            if not row:
                # Insert as a new row tagged with the right level
                try:
                    c.execute(
                        "INSERT INTO vocabulary "
                        "(level, word, phonetic, pos, translation, frequency, "
                        " star_rating, example_sentence, example_translation, tags) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            item.level, word,
                            p.get("phonetic", ""), p.get("pos", ""),
                            p.get("translation", ""), 50, 3,
                            p.get("example_sentence", ""),
                            p.get("example_translation", ""),
                            f"crawler:{item.source}",
                        ),
                    )
                    c.commit()
                    self._inserted += 1
                    return True
                except sqlite3.IntegrityError:
                    self._skipped += 1
                    return False
            # Update empty fields only — don't clobber existing data
            new_phonetic = p.get("phonetic", "") or row["phonetic"]
            new_translation = p.get("translation", "") or row["translation"]
            new_example = p.get("example_sentence", "") or row["example_sentence"]
            c.execute(
                "UPDATE vocabulary SET phonetic = ?, translation = ?, "
                "example_sentence = ? WHERE id = ?",
                (new_phonetic, new_translation, new_example, row["id"]),
            )
            c.commit()
        self._inserted += 1
        return True

    def _write_reading(self, item: RawItem) -> bool:
        p = item.payload
        title = (p.get("passage_title") or "").strip()
        if not self._is_new("reading", item.level, title):
            self._skipped += 1
            return False
        with self._conn() as c:
            c.execute(
                "INSERT INTO reading "
                "(level, year, session, passage_title, passage, questions, answers, "
                " analysis, topic_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.level, 0, "练习",
                    title, p.get("passage", ""),
                    p.get("questions", "[]"),
                    p.get("answers", ""),
                    p.get("analysis", ""),
                    p.get("topic_type", "综合"),
                ),
            )
            c.commit()
        self._inserted += 1
        return True

    def _write_listening(self, item: RawItem) -> bool:
        p = item.payload
        key = (p.get("audio_script") or "")[:120]
        if not self._is_new("listening", item.level, key):
            self._skipped += 1
            return False
        with self._conn() as c:
            c.execute(
                "INSERT INTO listening "
                "(level, year, session, section, audio_script, questions, answers, "
                " analysis, topic_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.level, 0, "练习",
                    p.get("section", "短对话"),
                    p.get("audio_script", ""),
                    p.get("questions", "[]"),
                    p.get("answers", ""),
                    p.get("analysis", ""),
                    p.get("topic_type", "综合"),
                ),
            )
            c.commit()
        self._inserted += 1
        return True

    def _write_translation(self, item: RawItem) -> bool:
        p = item.payload
        zh = (p.get("chinese_text") or "")[:120]
        if not self._is_new("translation", item.level, zh):
            self._skipped += 1
            return False
        with self._conn() as c:
            c.execute(
                "INSERT INTO translation "
                "(level, year, session, chinese_text, english_reference, key_points, "
                " analysis, topic_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.level, 0, "练习",
                    p.get("chinese_text", ""),
                    p.get("english_reference", ""),
                    p.get("key_points", ""),
                    p.get("analysis", ""),
                    p.get("topic_type", "综合"),
                ),
            )
            c.commit()
        self._inserted += 1
        return True

    def _write_writing(self, item: RawItem) -> bool:
        p = item.payload
        topic = (p.get("topic") or p.get("requirements") or "")[:120]
        if not self._is_new("writing", item.level, topic):
            self._skipped += 1
            return False
        with self._conn() as c:
            c.execute(
                "INSERT INTO writing "
                "(level, year, session, topic, requirements, sample_essay, key_phrases, "
                " category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.level, 0, "练习",
                    p.get("topic", ""),
                    p.get("requirements", ""),
                    p.get("sample_essay", ""),
                    p.get("key_phrases", ""),
                    p.get("category", "综合"),
                ),
            )
            c.commit()
        self._inserted += 1
        return True

    # ---------- summary ----------
    def report(self) -> dict[str, int]:
        return {"inserted": self._inserted, "skipped": self._skipped}


def write_all(writer: DBWriter, items: Iterable[RawItem]) -> dict[str, int]:
    for item in items:
        writer.write(item)
    return writer.report()
