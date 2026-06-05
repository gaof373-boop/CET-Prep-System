"""Strict CET-4/CET-6 dedup.

Removes vocabulary rows tagged as ``CET6`` whose ``word`` is also
present under ``CET4`` (the lower level wins, per the 2016 outline
rule that CET-6 = CET-4 + ~1500 NEW academic words).
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

    cet4_words = {r["word"].lower() for r in dm.list_vocabulary("CET4")}
    cet6_words = {r["word"].lower() for r in dm.list_vocabulary("CET6")}
    overlap = cet4_words & cet6_words
    print(f"CET-4 总词数: {len(cet4_words)}")
    print(f"CET-6 总词数: {len(cet6_words)}")
    print(f"重叠: {len(overlap)} 词")

    if not overlap:
        print("没有重叠,无需清理。")
        return 0

    # Delete CET-6 rows whose word is also in CET-4
    removed = 0
    with dm._conn() as c:  # type: ignore[attr-defined]
        for w in overlap:
            cur = c.execute(
                "DELETE FROM vocabulary WHERE level = 'CET6' AND word = ?",
                (w,),
            )
            removed += cur.rowcount
        c.commit()
    print(f"已删除 {removed} 个重复的 CET-6 行 (CET-4 那份保留)。")
    print()
    print("清理后:")
    print(f"  CET-4 词数: {dm.section_stats('CET4')['vocab']}")
    print(f"  CET-6 词数: {dm.section_stats('CET6')['vocab']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
