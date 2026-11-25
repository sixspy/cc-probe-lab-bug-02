"""贯验分页双写两轨（工程形态乙）。

- 旧轨：缓冲首页（写死首页上限 20）快照进只读归档 archive_*；
- 新轨：立 live_flag，active_read 切到 live_flag，现行贯验读全表游标集；
- 对齐结论只服从真实全量贯验：撕裂/未扫/争用时 chip 与 truth 同色，aligned 不得为真。
"""
from __future__ import annotations

import json

from app.db import 连接
from app.services import pageblind as core

_SLUG = "pageblind"
_TITLE = "贯验分页"
_OK = "对齐已亮"
_BAD = "尾页未扫"
_TEAR = "尾页撕裂"


def _honest_marker(scan: dict) -> str:
    if scan.get("是否对齐") and int(scan.get("未扫行数", 1)) == 0 and not scan.get("争用"):
        return _OK
    if int(scan.get("未扫行数", 0)) or scan.get("争用"):
        return _BAD
    return _TEAR


def apply_dualwrite(note: str = "") -> dict:
    # 真相来源：真实全量游标贯验（不落历史也可，这里取只读稳定快照）。
    from app.services import 贯验
    scan = 贯验.只读快照()
    marker = _honest_marker(scan)
    ok = marker == _OK

    conn = 连接()
    try:
        core._ensure(conn)
        # 清掉上一轮归档投影，避免计数无限累积。
        # 下划线在 LIKE 里是通配，但此处键命名规整，与 core.archive_rows 同模式即可。
        old = conn.execute(
            "SELECT 键 FROM 探栏元 WHERE 键 LIKE ?", (f"{_SLUG}_archive_%",)
        ).fetchall()
        for r in old:
            conn.execute("DELETE FROM 探栏元 WHERE 键=?", (r["键"],))

        # 旧轨首页快照：只取缓冲首页二十行，逐行只读归档。
        first = conn.execute(
            "SELECT * FROM 入栏缓冲 ORDER BY rowid LIMIT ?",
            (int(getattr(贯验, "首页上限", 20)),),
        ).fetchall()
        if first:
            for i, row in enumerate(first):
                d = dict(row)
                编号 = str(d.get("报文编号") or i)
                payload = json.dumps(d, ensure_ascii=False, default=str, sort_keys=True)
                core._set(conn, f"{_SLUG}_archive_row_{i:04d}_{编号}", payload)
        else:
            # 空库也留一份显式空快照，保证“首页快照已归档”这一轨可验收。
            core._set(
                conn,
                f"{_SLUG}_archive_snapshot_empty",
                json.dumps({"空快照": True, "首页上限": 20, "说明": "缓冲为空"},
                           ensure_ascii=False),
            )

        fp = str(scan.get("指纹") or scan.get("扫描指纹") or "")
        live = f"live-full_cursor-{fp[:12]}" if fp else "live-full_cursor"
        core._set(conn, f"{_SLUG}_live_flag", live)
        # 读轨切换是工程动作：无论真相好坏都切到新轨；是否绿由真相位决定。
        core._set(conn, f"{_SLUG}_active_read", "live_flag")
        core._set(conn, f"{_SLUG}_dual_chip", marker)
        core._set(conn, f"{_SLUG}_dual_truth", marker)
        core._set(conn, f"{_SLUG}_dual_note", note or _TITLE)
        core._set(conn, f"{_SLUG}_panel_chip", marker)
        core._set(conn, f"{_SLUG}_truth", marker)
        core._set(conn, f"{_SLUG}_dual_fp", fp)
        conn.commit()
    finally:
        conn.close()

    dash = core.dashboard()
    return {
        "ok": True,
        "dual_chip": marker,
        "truth": core.truth_flag(),
        "panel_chip": core.panel_chip(),
        "active_read": core.active_read_ref(),
        "archive_count": len(core.archive_rows()),
        "live_flag": core.live_flag(),
        "aligned": bool(dash["aligned"]),
        "未扫行数": dash["未扫行数"],
        "扫描范围": dash["扫描范围"],
        "灯色": dash["灯色"],
        "note": note or _TITLE,
    }


def dual_board() -> dict:
    out = apply_dualwrite()
    dash = core.dashboard()
    return {
        "dual_chip": out["dual_chip"],
        "truth": core.truth_flag(),
        "active_read": core.active_read_ref(),
        "archive": core.archive_rows(),
        "archive_count": out["archive_count"],
        "live_flag": core.live_flag(),
        "dash": dash,
        "aligned": dash["aligned"],
        "fate": "dualwrite",
        # 不再硬编码 mismatch：由真实 aligned 决定。
        "panel_pack_mismatch": bool(dash.get("panel_pack_mismatch")),
        "title": f"{_TITLE}双写面",
        "扫描范围": dash["扫描范围"],
        "未扫行数": dash["未扫行数"],
    }
