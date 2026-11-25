"""贯验分页切流账册（工程形态甲：审计账册）。

全量扫描指纹耐久落账，active_read 切到 cutover_book，
reject_refresh=1 拒绝回刷旧轨 / 拒绝带未扫收口。
真相位必须来自真实全量贯验，而不是只刷装饰芯片。
"""
from __future__ import annotations

from app.db import 连接
from app.services import pageblind as core

_SLUG = "pageblind"
_TITLE = "贯验分页"
_OK = "对齐已亮"


def append_cutover(ref_id: int, note: str = "") -> dict:
    # 先跑真实全量贯验：写栏贯验历史 + 贯验扫描审计账 + 同步指纹/读轨/真相。
    from app.services import 贯验
    scan = 贯验.跑一次()

    conn = 连接()
    try:
        core._ensure(conn)
        core._set(conn, f"{_SLUG}_cutover_note_{ref_id}", note or _TITLE)
        core._set(conn, f"{_SLUG}_cutover_ref", str(ref_id))
        # 耐久指纹 + 拒回刷 + 读轨改写（_同步台灯已写，这里再钉死一次）。
        core._set(conn, f"{_SLUG}_cutover_fp", scan["指纹"])
        core._set(conn, f"{_SLUG}_reject_refresh", "1")
        if int(scan["未扫行数"]) == 0 and not scan["争用"]:
            core._set(conn, f"{_SLUG}_active_read", "cutover_book")
        conn.commit()
    finally:
        conn.close()

    dash = core.dashboard()
    return {
        "ok": True,
        "ref_id": ref_id,
        "note": note,
        "panel": core.panel_chip(),
        "truth": core.truth_flag(),
        "active_read": core.active_read_ref(),
        "cutover_fp": core.cutover_fp(),
        "reject_refresh": core.reject_refresh(),
        "aligned": dash["aligned"],
        "未扫行数": dash["未扫行数"],
        "扫描范围": dash["扫描范围"],
        "灯色": dash["灯色"],
        "scan": {
            "指纹": scan["指纹"],
            "已汇总缓冲": scan["已汇总缓冲"],
            "汇总报文": scan["汇总报文"],
            "是否对齐": scan["是否对齐"],
        },
    }


def board() -> dict:
    dash = core.dashboard()
    dash["fate"] = "cutover_book"
    # panel_pack_mismatch 已由 core.snapshot 按真实 aligned 计算，不再硬编码 True。
    return dash
