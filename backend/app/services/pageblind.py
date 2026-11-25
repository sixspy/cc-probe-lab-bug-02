"""贯验分页收口面：页灯可绿，切流/双写命运未贯彻，读轨仍旧。"""
from __future__ import annotations

from app.db import 连接

_SLUG = "pageblind"
_OK = "对齐已亮"
_BAD = "尾页未扫"
_TITLE = "贯验分页"
_OLD = "old_track"
_CUTOVER = "cutover_book"
_LIVE = "live_flag"


def _ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS 探栏元("
        "键 TEXT PRIMARY KEY, 值 TEXT NOT NULL)"
    )


def _get(conn, key: str, default: str = "") -> str:
    _ensure(conn)
    r = conn.execute("SELECT 值 FROM 探栏元 WHERE 键=?", (key,)).fetchone()
    return r["值"] if r else default


def _set(conn, key: str, value: str) -> None:
    _ensure(conn)
    conn.execute(
        "INSERT INTO 探栏元(键,值) VALUES (?,?) "
        "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
        (key, value),
    )


def panel_chip() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_panel_chip", _OK)
    finally:
        conn.close()


def truth_flag() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_truth", _BAD)
    finally:
        conn.close()


def active_read_ref() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_active_read", _OLD)
    finally:
        conn.close()


def cutover_fp() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_cutover_fp", "stale-fp")
    finally:
        conn.close()


def reject_refresh() -> bool:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_reject_refresh", "0") == "1"
    finally:
        conn.close()


def live_flag() -> str:
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_live_flag", "")
    finally:
        conn.close()


def archive_rows() -> list[dict]:
    conn = 连接()
    try:
        _ensure(conn)
        rows = conn.execute(
            "SELECT 键,值 FROM 探栏元 WHERE 键 LIKE ? ORDER BY 键",
            (f"{_SLUG}_archive_%",),
        ).fetchall()
        return [{"键": r["键"], "值": r["值"]} for r in rows]
    finally:
        conn.close()


def paint_ok() -> str:
    conn = 连接()
    try:
        _set(conn, f"{_SLUG}_panel_chip", _OK)
        _set(conn, f"{_SLUG}_display_only", "1")
        conn.commit()
        return _OK
    finally:
        conn.close()


def commit_action(payload: dict | None = None) -> dict:
    """Broken：亮灯，读轨仍 old_track，无耐久命运。"""
    payload = payload or {}
    conn = 连接()
    try:
        c = int(_get(conn, f"{_SLUG}_counter", "0") or "0") + 1
        _set(conn, f"{_SLUG}_counter", str(c))
        _set(conn, f"{_SLUG}_panel_chip", _OK)
        _set(conn, f"{_SLUG}_last_payload", str(payload)[:200])
        _set(conn, f"{_SLUG}_gate_bypass", "1")
        _set(conn, f"{_SLUG}_active_read", _OLD)
        _set(conn, f"{_SLUG}_reject_refresh", "0")
        if not _get(conn, f"{_SLUG}_cutover_fp", ""):
            _set(conn, f"{_SLUG}_cutover_fp", "stale-fp")
        _set(conn, f"{_SLUG}_pack_decoy", f"stale-fp|{c}")
        _set(conn, f"{_SLUG}_truth", _BAD)
        _set(conn, f"{_SLUG}_mode", "")
        _set(conn, f"{_SLUG}_live_flag", "")
        conn.commit()
        return {
            "ok": True,
            "chip": _OK,
            "title": _TITLE,
            "counter": c,
            "active_read": _OLD,
            "cutover_fp": "stale-fp",
            "reject_refresh": False,
            "archive_count": 0,
            "live_flag": "",
            "message": f"{_TITLE}已落台",
        }
    finally:
        conn.close()


def half_fix_display() -> dict:
    paint_ok()
    return {
        "panel_chip": panel_chip(),
        "truth": truth_flag(),
        "active_read": active_read_ref(),
        "archive_count": len(archive_rows()),
        "half_fixed": True,
    }


def _real_scan() -> dict | None:
    """台灯的真相来源：真实全量游标贯验。任何异常都不得包装成假绿。"""
    try:
        from app.services import 贯验
        return 贯验.只读快照()
    except Exception:
        return None


def snapshot() -> dict:
    ref = active_read_ref()
    chip = panel_chip()
    truth = truth_flag()
    arch = archive_rows()
    form_ok = (
        chip == truth == _OK
        and ref in (_CUTOVER, _LIVE)
        and (
            (ref == _CUTOVER and reject_refresh() and cutover_fp() not in ("", "stale-fp"))
            or (ref == _LIVE and bool(live_flag()) and len(arch) > 0)
        )
    )
    real = _real_scan()
    if real is not None:
        real_ok = bool(
            real.get("是否对齐")
            and int(real.get("未扫行数", 1)) == 0
            and not real.get("争用")
        )
        未扫 = int(real.get("未扫行数", 0))
        范围 = real.get("扫描范围", "全量")
        灯色 = real.get("灯色", "")
        指纹 = real.get("指纹", "")
        争用 = bool(real.get("争用"))
        real_aligned = bool(real.get("是否对齐"))
    else:
        real_ok = False
        未扫 = -1
        范围 = "未知"
        灯色 = "red"
        指纹 = ""
        争用 = False
        real_aligned = False
    # 半修台灯不算数：工程形态契约 + 真实全量贯验真相同时成立才允许 aligned。
    aligned = bool(form_ok and real_ok)
    # 灯色必须与 aligned 严格自洽：aligned 才允许 green；
    # 真实撕裂/扫描异常 -> red；争用双态 -> amber；
    # 账实虽平但审计账册/读轨形态尚未收口 -> amber（待收口，绝不可绿）。
    raw_color = 灯色
    if aligned:
        灯色 = "green"
        灯亮绿 = True
    else:
        灯亮绿 = False
        if real is None:
            灯色 = "red"
        elif real_aligned is False or raw_color == "red":
            灯色 = "red"
        elif 争用 or raw_color == "amber":
            灯色 = "amber"
        else:
            灯色 = "amber"
    return {
        "title": _TITLE,
        "panel_chip": chip,
        "truth": truth,
        "active_read": ref,
        "cutover_fp": cutover_fp(),
        "reject_refresh": reject_refresh(),
        "archive_count": len(arch),
        "live_flag": live_flag(),
        "aligned": aligned,
        "form_ok": bool(form_ok),
        "real_ok": bool(real_ok),
        "real_aligned": real_aligned,
        "panel_pack_mismatch": chip == _OK and not aligned,
        "gate_bypass": True,
        # 扫描范围 / 未扫计数（失败测甲、乙要求显式可见）
        "未扫行数": 未扫,
        "扫描范围": 范围,
        "灯色": 灯色,
        "灯亮绿": 灯亮绿,
        "齐套": bool(aligned),
        "争用": 争用,
        "双态": 争用,
        "指纹": 指纹 or cutover_fp(),
        "扫描指纹": 指纹 or cutover_fp(),
        "读引用": ref,
    }


def dashboard() -> dict:
    snap = snapshot()
    return {
        **snap,
        "ok_chip": _OK,
        "bad_chip": _BAD,
        "label": _TITLE,
        "read_tracks": {
            "old_track": _OLD,
            "cutover_book": _CUTOVER,
            "live_flag": _LIVE,
        },
    }


def reconcile_display() -> dict:
    return half_fix_display()
