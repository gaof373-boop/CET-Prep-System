"""一键灌装 CET-4 / CET-6 写作/阅读/翻译 真题(教学材料级,合规)。

Usage::

    python -m crawler.bulk_load_exams

会自动:
1. 调用 init_database() 触发 schema 迁移
2. 从 real_exams.py / real_exams_reading.py / real_exams_translation.py
   读取数据
3. 写入 DB,严格按 (level, year, session, topic) / (level, year, session, title)
   去重
4. 打印清晰统计报告
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db_init import init_database  # noqa: E402
from core.data_manager import DataManager  # noqa: E402


def main() -> int:
    init_database()
    dm = DataManager()

    # ----- 写作 -----
    from crawler.sources.real_exams import WRITING_CET4, WRITING_CET6

    print("=" * 60)
    print("  📚  开始灌装写作真题")
    print("=" * 60)
    w4_added = 0
    for w in WRITING_CET4:
        new_id = dm.upsert_writing(
            level="CET4",
            year=int(w.get("year", 0)),
            session=str(w.get("session", "")),
            title=str(w.get("title", "")),
            topic=str(w.get("title", "")),  # 用 title 兼当 topic
            requirements=str(w.get("requirements", "")),
            sample_essay=str(w.get("sample_essay", "")),
            key_phrases=str(w.get("key_phrases", "")),
            category=str(w.get("category", "")),
            highlights=json_dumps_safe(w.get("highlights", [])),
        )
        if new_id is not None:
            w4_added += 1

    w6_added = 0
    for w in WRITING_CET6:
        new_id = dm.upsert_writing(
            level="CET6",
            year=int(w.get("year", 0)),
            session=str(w.get("session", "")),
            title=str(w.get("title", "")),
            topic=str(w.get("title", "")),
            requirements=str(w.get("requirements", "")),
            sample_essay=str(w.get("sample_essay", "")),
            key_phrases=str(w.get("key_phrases", "")),
            category=str(w.get("category", "")),
            highlights=json_dumps_safe(w.get("highlights", [])),
        )
        if new_id is not None:
            w6_added += 1

    # ----- 阅读 -----
    from crawler.sources.real_exams_reading import READING_CET4, READING_CET6

    print("=" * 60)
    print("  📖  开始灌装阅读真题")
    print("=" * 60)
    r4_added = 0
    for r in READING_CET4:
        new_id = dm.upsert_reading(
            level="CET4",
            year=int(r.get("year", 0)),
            session=str(r.get("session", "")),
            passage_title=str(r.get("title", "")),
            passage=str(r.get("passage", "")),
            questions=json_dumps_safe(r.get("questions", [])),
            answers=str(r.get("answers", "")),
            analysis=str(r.get("analysis", "")),
            topic_type=str(r.get("topic_type", "")),
            options=json_dumps_safe(r.get("questions", [])),  # 兼容老字段
            answer="",  # 单字母答案留空,UI 用 answers 字段
        )
        if new_id is not None:
            r4_added += 1

    r6_added = 0
    for r in READING_CET6:
        new_id = dm.upsert_reading(
            level="CET6",
            year=int(r.get("year", 0)),
            session=str(r.get("session", "")),
            passage_title=str(r.get("title", "")),
            passage=str(r.get("passage", "")),
            questions=json_dumps_safe(r.get("questions", [])),
            answers=str(r.get("answers", "")),
            analysis=str(r.get("analysis", "")),
            topic_type=str(r.get("topic_type", "")),
            options=json_dumps_safe(r.get("questions", [])),
            answer="",
        )
        if new_id is not None:
            r6_added += 1

    # ----- 翻译 -----
    from crawler.sources.real_exams_translation import (
        TRANSLATION_CET4, TRANSLATION_CET6,
    )

    print("=" * 60)
    print("  🌐  开始灌装翻译真题")
    print("=" * 60)
    t4_added = 0
    for t in TRANSLATION_CET4:
        new_id = dm.upsert_translation(
            level="CET4",
            year=int(t.get("year", 0)),
            session=str(t.get("session", "")),
            chinese_text=str(t.get("chinese_text", "")),
            english_translation=str(t.get("english_reference", "")),
            key_terms=str(t.get("key_points", "")),
            analysis=str(t.get("analysis", "")),
            topic_type=str(t.get("title", "")),
        )
        if new_id is not None:
            t4_added += 1

    t6_added = 0
    for t in TRANSLATION_CET6:
        new_id = dm.upsert_translation(
            level="CET6",
            year=int(t.get("year", 0)),
            session=str(t.get("session", "")),
            chinese_text=str(t.get("chinese_text", "")),
            english_translation=str(t.get("english_reference", "")),
            key_terms=str(t.get("key_points", "")),
            analysis=str(t.get("analysis", "")),
            topic_type=str(t.get("title", "")),
        )
        if new_id is not None:
            t6_added += 1

    # ----- 最终统计 -----
    print()
    print("=" * 60)
    print("  ✅  灌装完成 — 最终统计报告")
    print("=" * 60)
    final = {
        "CET4 写作": dm.count_writing("CET4"),
        "CET6 写作": dm.count_writing("CET6"),
        "CET4 阅读": dm.count_reading("CET4"),
        "CET6 阅读": dm.count_reading("CET6"),
        "CET4 翻译": dm.count_translation("CET4"),
        "CET6 翻译": dm.count_translation("CET6"),
    }
    print(f"  ✅ 成功导入 CET4 写作  {w4_added} 篇    (DB 总数 {final['CET4 写作']})")
    print(f"  ✅ 成功导入 CET6 写作  {w6_added} 篇    (DB 总数 {final['CET6 写作']})")
    print(f"  ✅ 成功导入 CET4 阅读  {r4_added} 篇    (DB 总数 {final['CET4 阅读']})")
    print(f"  ✅ 成功导入 CET6 阅读  {r6_added} 篇    (DB 总数 {final['CET6 阅读']})")
    print(f"  ✅ 成功导入 CET4 翻译  {t4_added} 篇    (DB 总数 {final['CET4 翻译']})")
    print(f"  ✅ 成功导入 CET6 翻译  {t6_added} 篇    (DB 总数 {final['CET6 翻译']})")
    print()
    print(f"  本次总新增: 写作 {w4_added + w6_added}  阅读 {r4_added + r6_added}  翻译 {t4_added + t6_added}")
    print("=" * 60)
    return 0


def json_dumps_safe(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())