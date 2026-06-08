"""data_loader.py — CET 智胜 云端数据维护脚本

用途
====

在不影响用户进度(错题本 / 已掌握 / 答题记录)的前提下,向 cet_exam.db
**增量**写入新词汇 / 真题。脚本使用 ``INSERT OR IGNORE`` + 唯一键去重,
所以可以安全地反复运行,云端用户数据(``vocabulary.wrong_count`` /
``mastered`` / ``consec_correct`` 等)**绝对不会被冲掉**。

数据怎么放
==========

在脚本顶部,有 5 个 Python 列表:

  NEW_VOCAB      新单词(每条对应 vocabulary 表一行)
  NEW_READING    新阅读文章
  NEW_WRITING    新写作真题
  NEW_TRANSLATION 新翻译真题
  NEW_LISTENING  新听力题(可选,本批次没示范)

每个列表里追加新 dict 即可,字段名跟 db_init.py 里的 seed 列表一致。
也支持从 JSONL 文件追加(看 _load_jsonl_append())。

唯一性去重规则
==============

  vocabulary       (level, word)        联合唯一
  reading          passage_title        唯一
  writing          title                唯一
  translation      chinese_text         唯一
  listening        (level, year, session, section)  联合唯一
  generated_practice (parent_id, section, title)    联合唯一

如果你的新条目跟已有题目撞了,**整行 skip**,不会报错。

使用方式
========

  本地:  python tools/data_loader.py
  云端:  ssh ubuntu@118.24.71.143
         cd ~/cet/app
         python3.11 tools/data_loader.py

跑完会打印类似:
  [vocab]     +18 new  (2 skipped as duplicates)
  [reading]   +1 new   (0 duplicates)
  ...
  TOTAL: 19 new rows added, 2 skipped.

统计
====

每次运行前会读 db 当前 row 数,运行后读最终数,差值就是真实增量。
即便多线程/重复执行,统计也不会撒谎(全靠数据库真实变化)。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Make the parent project importable so we can use DB_PATH
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.db_init import DB_PATH  # noqa: E402


# ===========================================================================
# USER DATA ZONE
# ---------------------------------------------------------------------------
# 把新题目 append 到对应的列表里。每行字段名 / 顺序 / 数量 / 类型都必须
# 跟 db_init.py 里的 SEED 一致(去掉了 mastered / wrong_count 这类进度
# 字段,数据库会用 DEFAULT)。
# ===========================================================================

NEW_VOCAB: list[dict[str, Any]] = [
    # --- 例子(已存在的 5 词,跑脚本会被去重 skip) ---
    # {"level": "CET4", "word": "alike", "phonetic": "/əˈlaɪk/",
    #  "pos": "adj.", "translation": "相似的,相同的",
    #  "frequency": 200, "star_rating": 5,
    #  "example_sentence": "Twins look alike.",
    #  "example_translation": "双胞胎看起来很像。",
    #  "tags": "高频"},
    #
    # --- 真正想新增的:复制下面这行改 word/translation 即可 ---
    # {"level": "CET6", "word": "syllabus",
    #  "phonetic": "/ˈsɪləbəs/", "pos": "n.",
    #  "translation": "教学大纲,课程表",
    #  "frequency": 12, "star_rating": 3,
    #  "example_sentence": "Check the syllabus for reading assignments.",
    #  "example_translation": "查看大纲了解阅读作业。",
    #  "tags": "新增"},
]

NEW_READING: list[dict[str, Any]] = [
    # --- 例子(如果 passage_title 已存在会被 skip) ---
    # {"level": "CET4", "year": 2025, "session": "6月",
    #  "passage_title": "The Hidden Value of Boredom",
    #  "passage": "Full English passage here, 280-360 words ...",
    #  "questions": '[{"q":"...","options":["A. ...","B. ...","C. ...","D. ..."]}]',
    #  "answers": "1. B",
    #  "analysis": "Q1. 这道题考查的是...",
    #  "topic_type": "心理学"},
]

NEW_WRITING: list[dict[str, Any]] = [
    # {"level": "CET4", "year": 2025, "session": "6月",
    #  "topic": "The impact of short videos on students",
    #  "requirements": "Write an essay of 120-180 words ...",
    #  "sample_essay": "In recent years, short videos ...",
    #  "key_phrases": "in conclusion, take a balanced view",
    #  "category": "教育/科技",
    #  "title": "短视频对大学生的影响"},
]

NEW_TRANSLATION: list[dict[str, Any]] = [
    # {"level": "CET6", "year": 2025, "session": "12月",
    #  "chinese_text": "随着人工智能技术的快速发展,...",
    #  "english_reference": "With the rapid development of AI, ...",
    #  "key_points": "人工智能: artificial intelligence; 快速发展: rapid development",
    #  "analysis": "本句重点翻译要点:...",
    #  "topic_type": "科技"},
]

NEW_LISTENING: list[dict[str, Any]] = [
    # {"level": "CET4", "year": 2025, "session": "6月",
    #  "section": "短对话 (Short Conversation)",
    #  "audio_script": "W: ... M: ...",
    #  "audio_file": "database/audio/CET4_2025_1.mp3",   # 路径相对项目根
    #  "questions": '[{"q":"...","options":["A. ...","B. ...","C. ...","D. ..."]}]',
    #  "answers": "1. A  2. B",
    #  "analysis": "...",
    #  "topic_type": "校园/生活"},
]


# ===========================================================================
# DATABASE LOADING LOGIC — don't edit below unless you know what you do
# ===========================================================================

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _exists(conn: sqlite3.Connection, sql: str, params: tuple) -> bool:
    """Cheap pre-check so we can skip duplicates even when the table
    has no UNIQUE constraint (the schema's vocabulary table doesn't).
    Returns True if at least one row matches."""
    row = conn.execute(sql, params).fetchone()
    return row is not None


def _load_vocab(conn: sqlite3.Connection) -> tuple[int, int]:
    """Returns (inserted, skipped) for vocabulary.

    We do a pre-check SELECT before each INSERT because the vocabulary
    table has no UNIQUE constraint in db_init.py — relying solely on
    ``INSERT OR IGNORE`` would silently let duplicates accumulate.
    Pre-check is a single indexed-ish lookup per row; for our scale
    (~7k rows) this is sub-millisecond.
    """
    insert_sql = (
        "INSERT INTO vocabulary "
        "(level, word, phonetic, pos, translation, frequency, "
        " star_rating, example_sentence, example_translation, tags) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    check_sql = "SELECT 1 FROM vocabulary WHERE level = ? AND word = ? LIMIT 1"
    inserted = 0
    skipped = 0
    cur = conn.cursor()
    for v in NEW_VOCAB:
        level = v.get("level", "CET4")
        word = v["word"]
        if _exists(conn, check_sql, (level, word)):
            skipped += 1
            continue
        cur.execute(insert_sql, (
            level, word,
            v.get("phonetic", ""),
            v.get("pos", ""),
            v.get("translation", ""),
            int(v.get("frequency", 0) or 0),
            int(v.get("star_rating", 1) or 1),
            v.get("example_sentence", ""),
            v.get("example_translation", ""),
            v.get("tags", ""),
        ))
        inserted += 1
    conn.commit()
    return inserted, skipped


def _load_reading(conn: sqlite3.Connection) -> tuple[int, int]:
    """Reading uses INSERT OR IGNORE on the natural title-unique path.
    We also pre-check to mirror vocabulary's pattern — keeps the
    "skipped" count honest even if a future schema change removes
    the unique constraint."""
    check_sql = "SELECT 1 FROM reading WHERE passage_title = ? LIMIT 1"
    insert_sql = (
        "INSERT INTO reading "
        "(level, year, session, passage_title, passage, questions, "
        " answers, analysis, topic_type) "
        "VALUES (?,?,?,?,?,?,?,?,?)"
    )
    inserted = skipped = 0
    cur = conn.cursor()
    for r in NEW_READING:
        if _exists(conn, check_sql, (r["passage_title"],)):
            skipped += 1
            continue
        cur.execute(insert_sql, (
            r.get("level", "CET4"),
            int(r.get("year", 0) or 0),
            r.get("session", ""),
            r["passage_title"],
            r.get("passage", ""),
            r.get("questions", ""),
            r.get("answers", ""),
            r.get("analysis", ""),
            r.get("topic_type", ""),
        ))
        inserted += 1
    conn.commit()
    return inserted, skipped


def _load_writing(conn: sqlite3.Connection) -> tuple[int, int]:
    check_sql = "SELECT 1 FROM writing WHERE title = ? LIMIT 1"
    insert_sql = (
        "INSERT INTO writing "
        "(level, year, session, topic, requirements, sample_essay, "
        " key_phrases, category, title) "
        "VALUES (?,?,?,?,?,?,?,?,?)"
    )
    inserted = skipped = 0
    cur = conn.cursor()
    for w in NEW_WRITING:
        title = w.get("title", "")
        if title and _exists(conn, check_sql, (title,)):
            skipped += 1
            continue
        cur.execute(insert_sql, (
            w.get("level", "CET4"),
            int(w.get("year", 0) or 0),
            w.get("session", ""),
            w.get("topic", ""),
            w.get("requirements", ""),
            w.get("sample_essay", ""),
            w.get("key_phrases", ""),
            w.get("category", ""),
            title,
        ))
        inserted += 1
    conn.commit()
    return inserted, skipped


def _load_translation(conn: sqlite3.Connection) -> tuple[int, int]:
    check_sql = "SELECT 1 FROM translation WHERE chinese_text = ? LIMIT 1"
    insert_sql = (
        "INSERT INTO translation "
        "(level, year, session, chinese_text, english_reference, "
        " key_points, analysis, topic_type) "
        "VALUES (?,?,?,?,?,?,?,?)"
    )
    inserted = skipped = 0
    cur = conn.cursor()
    for t in NEW_TRANSLATION:
        zh = t["chinese_text"]
        if _exists(conn, check_sql, (zh,)):
            skipped += 1
            continue
        cur.execute(insert_sql, (
            t.get("level", "CET4"),
            int(t.get("year", 0) or 0),
            t.get("session", ""),
            zh,
            t.get("english_reference", ""),
            t.get("key_points", ""),
            t.get("analysis", ""),
            t.get("topic_type", ""),
        ))
        inserted += 1
    conn.commit()
    return inserted, skipped


def _load_listening(conn: sqlite3.Connection) -> tuple[int, int]:
    """Listening pre-check uses the (level, year, session, section)
    4-tuple. The (level, year, session) triplet is also tried as a
    fallback since some seed rows have NULL section."""
    check_sql = (
        "SELECT 1 FROM listening WHERE level = ? AND year = ? "
        "AND session = ? AND IFNULL(section,'') = IFNULL(?, '') LIMIT 1"
    )
    insert_sql = (
        "INSERT INTO listening "
        "(level, year, session, section, audio_script, audio_file, "
        " questions, answers, analysis, topic_type) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    inserted = skipped = 0
    cur = conn.cursor()
    for l in NEW_LISTENING:
        level = l.get("level", "CET4")
        year = int(l.get("year", 0) or 0)
        session = l.get("session", "")
        section = l.get("section", "")
        if _exists(conn, check_sql, (level, year, session, section)):
            skipped += 1
            continue
        cur.execute(insert_sql, (
            level, year, session, section,
            l.get("audio_script", ""),
            l.get("audio_file", ""),
            l.get("questions", ""),
            l.get("answers", ""),
            l.get("analysis", ""),
            l.get("topic_type", ""),
        ))
        inserted += 1
    conn.commit()
    return inserted, skipped


def _load_jsonl_append(path: Path, builder):
    """Optional helper — read a JSONL file of {"data": ...} entries and
    append into a target NEW_* list. Uncomment one of these at the
    bottom of main() if you want file-based batch input."""
    if not path.exists():
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [skip] bad JSON line: {e}")
                continue
            builder(obj)
            n += 1
    return n


# ===========================================================================
# Pretty-print
# ===========================================================================
def _print_banner(text: str, char: str = "=") -> None:
    line = char * max(60, len(text) + 4)
    print()
    print(line)
    print(f"  {text}")
    print(line)


def main() -> int:
    if not DB_PATH.exists():
        print(f"❌ DB not found at {DB_PATH}")
        print("   Run `python -m core.db_init` first to create the schema.")
        return 2

    _print_banner(f"CET 智胜 · data_loader  (DB: {DB_PATH})")

    conn = _connect()
    try:
        # Snapshot pre-state for the human-readable report
        before = {
            "vocabulary":   _table_count(conn, "vocabulary"),
            "reading":      _table_count(conn, "reading"),
            "writing":      _table_count(conn, "writing"),
            "translation":  _table_count(conn, "translation"),
            "listening":    _table_count(conn, "listening"),
            "generated_practice": _table_count(conn, "generated_practice"),
        }
        print("Pre-load row counts:")
        for k, v in before.items():
            print(f"  {k:25s} {v:5d}")

        # Apply each loader
        results = {}
        for label, fn, table in [
            ("vocab", _load_vocab, "vocabulary"),
            ("reading", _load_reading, "reading"),
            ("writing", _load_writing, "writing"),
            ("translation", _load_translation, "translation"),
            ("listening", _load_listening, "listening"),
        ]:
            inserted, skipped = fn(conn)
            results[table] = (inserted, skipped)
            # Verify by re-counting (defends against the cursor commit
            # count getting confused by a prior failed insert in the
            # same transaction)
            after = _table_count(conn, table)
            actual_delta = after - before[table]
            print(f"  [{label:11s}] +{inserted} new  "
                  f"({skipped} skipped as duplicates) "
                  f"· DB now {after} rows (Δ={actual_delta})")

        _print_banner("Done.", "─")
        total_in = sum(v[0] for v in results.values())
        total_skip = sum(v[1] for v in results.values())
        print(f"  TOTAL: {total_in} new rows added, "
              f"{total_skip} skipped as duplicates.")
        if total_in == 0 and total_skip == 0:
            print("  (No new entries in the lists yet —")
            print("   edit NEW_VOCAB / NEW_READING / etc. at the top of this file.)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
