"""列表与栏规。"""
from __future__ import annotations
from app.db import 连接
from app.services import 校验


def 栏规() -> dict:
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()}
    finally:
        conn.close()


def 改栏规(体: dict) -> dict:
    错 = 校验.校验栏规补丁(体 or {})
    if 错:
        return {"错误": 校验.摘要错误(错), "栏规": 栏规()}
    conn = 连接()
    try:
        for k, v in (体 or {}).items():
            conn.execute(
                "INSERT INTO 栏规(键,值) VALUES (?,?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
                (str(k), str(v)),
            )
        conn.commit()
        return 栏规()
    finally:
        conn.close()


def 站点列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 站点源 ORDER BY 源键").fetchall()]
    finally:
        conn.close()


def 报文列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 观测报文 ORDER BY 观测时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 缓冲列表(命运: str | None = None) -> list[dict]:
    conn = 连接()
    try:
        if 命运:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM 入栏缓冲 WHERE 命运=? ORDER BY 观测时", (命运,)
                ).fetchall()
            ]
        return [dict(r) for r in conn.execute("SELECT * FROM 入栏缓冲 ORDER BY 观测时").fetchall()]
    finally:
        conn.close()


def 汇总列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 站点汇总账 ORDER BY 物化时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 坏点列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 坏点匣 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 贯验列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 栏贯验 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 概览():
    # pageblind panel inject
    pass


def __概览_orig():
    raise RuntimeError


def 概览_broken_placeholder():
    return {}


def 概览() -> dict:
    conn = 连接()
    try:
        out = {
            "观测报文": conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"],
            "在栏": conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'").fetchone()["c"],
            "站点汇总": conn.execute("SELECT COUNT(*) AS c FROM 站点汇总账").fetchone()["c"],
            "坏点": conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"],
            "栏规": 栏规(),
        }
    finally:
        conn.close()
    # 探栏台水位卡片：齐套结论必须来自真实全量游标贯验，绝不把未扫行当齐套。
    try:
        from app.services import 贯验
        scan = 贯验.只读快照()
        未扫 = int(scan.get("未扫行数", 1))
        争用 = bool(scan.get("争用"))
        齐套 = bool(scan.get("是否对齐")) and 未扫 == 0 and not 争用
        out.update({
            "贯验齐套": 齐套,
            "齐套": 齐套,
            "是否对齐": bool(scan.get("是否对齐")),
            "未扫行数": 未扫,
            "扫描范围": scan.get("扫描范围", "全量"),
            "灯色": scan.get("灯色", "red"),
            "对齐灯": scan.get("对齐灯", "红"),
            "灯亮绿": bool(scan.get("灯亮绿")) and 齐套,
            "读引用": scan.get("读引用", "full_cursor"),
            "扫描指纹": scan.get("指纹", ""),
            "争用": 争用,
            "双态": 争用,
            "已汇总缓冲": scan.get("已汇总缓冲"),
            "汇总报文": scan.get("汇总报文"),
        })
    except Exception as e:  # 扫描自身故障时不得假绿
        out.update({
            "贯验齐套": False,
            "齐套": False,
            "是否对齐": False,
            "未扫行数": -1,
            "扫描范围": "未知（贯验扫描异常）",
            "灯色": "red",
            "对齐灯": "红",
            "灯亮绿": False,
            "争用": False,
            "双态": False,
            "贯验异常": repr(e),
        })
    return out


def 装载批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,时刻,入流,入栏,坏点 FROM 装载批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 结栏批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,栏号,时刻,汇总数 FROM 结栏批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 站点查(源键: str) -> dict | None:
    conn = 连接()
    try:
        r = conn.execute("SELECT * FROM 站点源 WHERE 源键=?", (源键,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()



def pageblind_齐套灯() -> dict:
    """齐套灯：齐套 == 对齐实值 == pageblind.aligned（真实全量扫描 + 工程形态契约）。

    旧实现只看装饰芯片是不是“对齐已亮”，而芯片播种即绿、真相位却是“尾页未扫”，
    造成新鲜库也假齐套。现在直接以 pageblind.dashboard() 的联剔结论为准，
    并显式带出扫描范围 / 未扫计数 / 灯色 / 读引用。
    """
    from app.services import pageblind as _m
    snap = _m.dashboard()
    齐套 = bool(snap.get("aligned"))
    return {
        "标题": snap.get("title"),
        "芯片": snap.get("panel_chip"),
        "真相": snap.get("truth"),
        # 三者必须严格同值，杜绝“芯片绿但实值假”的假齐套。
        "齐套": 齐套,
        "对齐实值": 齐套,
        "aligned": 齐套,
        "灯亮绿": bool(snap.get("灯亮绿")) and 齐套,
        "灯色": snap.get("灯色") or ("green" if 齐套 else "red"),
        "扫描范围": snap.get("扫描范围", "全量"),
        "未扫行数": snap.get("未扫行数", -1),
        "读引用": snap.get("读引用") or snap.get("active_read"),
        "active_read": snap.get("active_read"),
        "指纹": snap.get("指纹", ""),
        "争用": bool(snap.get("争用")),
        "双态": bool(snap.get("双态")),
        "form_ok": snap.get("form_ok"),
        "real_ok": snap.get("real_ok"),
        "账实对齐": snap.get("real_aligned"),
        "扫描齐套": snap.get("real_ok"),
        "panel_pack_mismatch": snap.get("panel_pack_mismatch", not 齐套),
    }
