"""栏贯验：全量游标读集对账，根除“分页盲区”。

旧实现把“已汇总缓冲”计数写死 LIMIT 20（只抽缓冲首页二十行），
尾页撕一行时首页样本仍可能与汇总数相等，于是对齐灯假绿；
说明服务仓情也拿不到未扫行数。

现形态（题面两案之审计账册案的内核，并兼容双写两轨投影）：
- 贯验读集用 rowid 游标逐页扫尽整张入栏缓冲 / 站点汇总账（全量，不写死首页）；
- 显式给出 扫描范围 / 已扫行数 / 未扫行数 与全量指纹；
- 单事务一致性快照 + 结栏纪元重试，解决“贯验途中结栏”的漏扫双态；
- 扫描完整且对账一致才亮绿灯；未扫尽 / 争用双态 / 撕裂一律非绿，并把真相同步给 pageblind 台灯。
"""
from __future__ import annotations

import hashlib
from collections import Counter

from app.db import 连接
from app.seed import 此刻

首页上限 = 20
页宽 = 20
读引用全量 = "full_cursor"

_OK = "对齐已亮"
_BAD = "尾页未扫"
_TEAR = "尾页撕裂"
EPOCH_KEY = "结栏_epoch"


# ---------------------------------------------------------------- 结栏纪元

def 读纪元(conn) -> int:
    try:
        r = conn.execute("SELECT 值 FROM 探栏元 WHERE 键=?", (EPOCH_KEY,)).fetchone()
        if r is None:
            return 0
        s = str(r["值"])
        return int(s) if s.lstrip("-").isdigit() else 0
    except Exception:
        return 0


def 推进纪元(conn) -> int:
    """结栏事务内调用：推进纪元，供并发贯验识别“途中有结栏提交”。"""
    ep = 读纪元(conn) + 1
    conn.execute(
        "INSERT INTO 探栏元(键,值) VALUES (?,?) "
        "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
        (EPOCH_KEY, str(ep)),
    )
    return ep


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO 探栏元(键,值) VALUES (?,?) "
        "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
        (key, value),
    )


def 当前栏号(conn) -> str:
    try:
        r = conn.execute("SELECT 值 FROM 栏规 WHERE 键='当前栏号'").fetchone()
        return str(r["值"]) if r else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- 全量游标扫描

def _游标全表(conn, 表: str, 额外列: str = "*") -> tuple[list[dict], int, int]:
    """rowid keyset 逐页扫尽全表。返回 (行列表, 页数, 表总行数)。"""
    行: list[dict] = []
    上次 = 0
    页数 = 0
    while True:
        rows = conn.execute(
            f"SELECT {额外列}, rowid AS _rid FROM {表} WHERE rowid > ? "
            "ORDER BY rowid LIMIT ?",
            (上次, 页宽),
        ).fetchall()
        if not rows:
            break
        页数 += 1
        for r in rows:
            d = dict(r)
            上次 = int(d.pop("_rid"))
            行.append(d)
        if len(rows) < 页宽:
            break
    总数 = conn.execute(f"SELECT COUNT(*) AS c FROM {表}").fetchone()["c"]
    return 行, 页数, int(总数)


def 全量快照(conn) -> dict:
    """在单个一致性读事务里扫尽缓冲与汇总账。调用方负责开关连接/重试。"""
    if getattr(conn, "in_transaction", False):
        conn.commit()
    conn.execute("BEGIN")
    try:
        缓冲, 缓冲页数, 缓冲总数 = _游标全表(conn, "入栏缓冲")
        汇总行, 汇总页数, _ = _游标全表(conn, "站点汇总账")
        在栏 = sum(1 for r in 缓冲 if r.get("命运") == "在栏")
        已汇总行 = [r for r in 缓冲 if r.get("命运") == "已汇总"]
        已汇总缓冲 = len(已汇总行)

        组缓冲: Counter = Counter(
            (r.get("栏号", ""), r.get("站点键", ""), r.get("指标键", ""))
            for r in 已汇总行
        )
        组汇总: Counter = Counter()
        汇总报文 = 0
        for r in 汇总行:
            n = int(r.get("报文数") or 0)
            汇总报文 += n
            组汇总[(r.get("栏号", ""), r.get("站点键", ""), r.get("指标键", ""))] += n

        组差异 = []
        for k in sorted(set(组缓冲) | set(组汇总)):
            if 组缓冲[k] != 组汇总[k]:
                组差异.append({
                    "组": "/".join(str(x) for x in k),
                    "缓冲": int(组缓冲[k]),
                    "汇总": int(组汇总[k]),
                })

        坏点 = int(conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"])

        # 三联（报文 / 缓冲 / 汇总）行级旁证：只做诊断，不改变计数契约。
        报文命 = {
            r["报文编号"]: r["命运"]
            for r in conn.execute("SELECT 报文编号, 命运 FROM 观测报文").fetchall()
        }
        缺行 = [r["报文编号"] for r in 已汇总行 if r.get("报文编号") not in 报文命]
        命运漂移 = [
            r["报文编号"] for r in 已汇总行
            if 报文命.get(r.get("报文编号")) not in (None, "已汇总")
        ]

        conn.execute("COMMIT")
    except Exception:
        if getattr(conn, "in_transaction", False):
            conn.execute("ROLLBACK")
        raise

    # 指纹：对全量缓冲读集按业务键排序后求哈希，任何尾页撕改都会变。
    h = hashlib.sha256()
    for r in sorted(缓冲, key=lambda x: str(x.get("报文编号"))):
        canon = "\x1f".join(str(r.get(k, "")) for k in
                            ("报文编号", "命运", "站点键", "指标键", "读数", "栏号"))
        h.update(canon.encode("utf-8"))
    指纹 = "fp-" + h.hexdigest()[:16]

    未扫行数 = max(0, 缓冲总数 - len(缓冲))
    计数齐 = 已汇总缓冲 == 汇总报文
    基础对齐 = 未扫行数 == 0 and 计数齐 and not 组差异

    return {
        "栏号": 当前栏号(conn),
        "在栏": 在栏,
        "已汇总缓冲": 已汇总缓冲,
        "汇总报文": int(汇总报文),
        "坏点": 坏点,
        "缓冲行": 缓冲,
        "扫描行数": len(缓冲),
        "已扫行数": len(缓冲),
        "缓冲总行数": 缓冲总数,
        "未扫行数": 未扫行数,
        "未扫": 未扫行数,
        "未扫行": 未扫行数,
        "unscanned_count": 未扫行数,
        "unscanned_rows": 未扫行数,
        "首页上限": 首页上限,
        "扫描页数": 缓冲页数,
        "汇总扫描页数": 汇总页数,
        "指纹": 指纹,
        "扫描指纹": 指纹,
        "fingerprint": 指纹,
        "cutover_fp": 指纹,
        "组差异": 组差异,
        "缺行": 缺行[:50],
        "命运漂移": 命运漂移[:50],
        "三联异常数": len(缺行) + len(命运漂移),
        "计数齐": 计数齐,
        "基础对齐": 基础对齐,
    }


def 定稿(data: dict, 争用: bool, attempts: int) -> dict:
    未扫 = int(data["未扫行数"])
    计数齐 = bool(data["计数齐"])
    组差异 = data["组差异"]
    硬撕裂 = (not 计数齐) or bool(组差异)
    aligned = (未扫 == 0) and (not 争用) and (not 硬撕裂)

    if aligned:
        灯色, 对齐灯, 灯亮绿 = "green", "绿", True
    elif (not 硬撕裂) and 未扫 == 0:
        # 计数本身相等，但扫描未稳定（结栏争用）→ 黄灯，绝不假绿。
        灯色, 对齐灯, 灯亮绿 = "amber", "黄", False
    else:
        灯色, 对齐灯, 灯亮绿 = "red", "红", False

    if aligned:
        说明 = (f"全量贯验对齐：已汇总缓冲={data['已汇总缓冲']} "
                f"汇总报文={data['汇总报文']}，扫尽{data['扫描行数']}行无未扫")
    else:
        bits = [f"已汇总缓冲={data['已汇总缓冲']}", f"汇总报文={data['汇总报文']}"]
        if 未扫:
            bits.append(f"未扫{未扫}行")
        if 组差异:
            bits.append(f"{len(组差异)}组不齐")
        if 争用:
            bits.append("贯验途中结栏并发，双态未稳定")
        说明 = ("撕裂：" if 硬撕裂 else "未收口：") + " ".join(bits)

    out = {
        "时刻": 此刻(),
        "在栏": data["在栏"],
        "在栏笔数": data["在栏"],
        "已汇总缓冲": data["已汇总缓冲"],
        "汇总报文": data["汇总报文"],
        "坏点": data["坏点"],
        "坏点笔数": data["坏点"],
        "是否对齐": bool(aligned),
        "对齐": bool(aligned),
        "说明": 说明,
        # 扫描范围契约
        "扫描范围": "全量",
        "范围码": "full",
        "scan_scope": "full_cursor",
        "扫描方式": "全表游标集",
        "读引用": 读引用全量,
        "active_read": 读引用全量,
        "scan_ref": 读引用全量,
        "扫描行数": data["扫描行数"],
        "已扫行数": data["已扫行数"],
        "缓冲总行数": data["缓冲总行数"],
        "未扫行数": 未扫,
        "未扫": 未扫,
        "未扫行": 未扫,
        "unscanned_count": 未扫,
        "unscanned_rows": 未扫,
        "首页上限": 首页上限,
        "扫描页数": data["扫描页数"],
        "指纹": data["指纹"],
        "扫描指纹": data["扫描指纹"],
        "fingerprint": data["fingerprint"],
        "cutover_fp": data["cutover_fp"],
        # 争用双态
        "争用": bool(争用),
        "双态": bool(争用),
        "contention": bool(争用),
        "dual_state": bool(争用),
        "attempts": attempts,
        # 灯
        "灯色": 灯色,
        "对齐灯": 对齐灯,
        "灯亮绿": bool(灯亮绿),
        "green": bool(灯亮绿),
        "齐套": bool(aligned),
        # 明细
        "组差异": 组差异,
        "缺行": data["缺行"],
        "命运漂移": data["命运漂移"],
        "三联异常数": data["三联异常数"],
        "栏号": data.get("栏号", ""),
    }
    return out


def 执行只读贯验(重试: int = 8) -> dict:
    """带结栏纪元重试的稳定全量贯验，不落任何库。"""
    import time

    last: dict | None = None
    attempts = 1
    for attempt in range(1, 重试 + 1):
        attempts = attempt
        conn = 连接()
        try:
            e0 = 读纪元(conn)
            data = 全量快照(conn)
            e1 = 读纪元(conn)
            last = data
            if e0 == e1:
                return 定稿(data, False, attempt)
        except Exception:
            # 并发写锁等瞬时错误：退避后用新连接重试，绝不把半成品当对齐。
            if attempt >= 重试:
                raise
            time.sleep(0.02 * attempt)
        finally:
            conn.close()
    return 定稿(last, True, attempts)  # type: ignore[arg-type]


def 只读快照() -> dict:
    """不落库的贯验快照，供页面预览 / 说明服务 / 齐套灯读取。"""
    return 执行只读贯验()


def _同步台灯(conn, r: dict) -> None:
    """贯验扫描范围与对齐灯联剔：台灯/真相位一律服从全量扫描结果。"""
    chip = _OK if r["是否对齐"] else (_BAD if (r["未扫行数"] or r["争用"]) else _TEAR)
    _set_meta(conn, "pageblind_panel_chip", chip)
    _set_meta(conn, "pageblind_truth", chip)
    _set_meta(conn, "pageblind_未扫行数", str(r["未扫行数"]))
    _set_meta(conn, "pageblind_扫描范围", r["扫描范围"])
    _set_meta(conn, "pageblind_灯色", r["灯色"])
    if int(r["未扫行数"]) == 0 and not r["争用"]:
        # 审计账册案：全量指纹落账、拒回刷。读轨若已显式选了双写 live_flag，则保留该选择，
        # 不能被一次例行贯验静默改回 cutover_book；old_track/空值才切到 cutover_book。
        现有轨 = ""
        try:
            row = conn.execute(
                "SELECT 值 FROM 探栏元 WHERE 键='pageblind_active_read'"
            ).fetchone()
            现有轨 = str(row["值"]) if row else ""
        except Exception:
            现有轨 = ""
        if 现有轨 != "live_flag":
            _set_meta(conn, "pageblind_active_read", "cutover_book")
        _set_meta(conn, "pageblind_reject_refresh", "1")
        _set_meta(conn, "pageblind_cutover_fp", r["指纹"])


def 跑一次() -> dict:
    r = 执行只读贯验()
    conn = 连接()
    try:
        cur = conn.execute(
            """INSERT INTO 栏贯验
               (时刻,在栏笔数,汇总报文数,坏点笔数,是否对齐,说明,
                扫描范围,未扫行数,扫描行数,指纹,读引用,灯色,争用)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["时刻"], r["在栏"], r["汇总报文"], r["坏点"],
             1 if r["是否对齐"] else 0, r["说明"],
             r["扫描范围"], r["未扫行数"], r["扫描行数"], r["指纹"],
             r["读引用"], r["灯色"], 1 if r["争用"] else 0),
        )
        r["编号"] = cur.lastrowid
        conn.execute(
            """INSERT INTO 贯验扫描账
               (时刻,栏号,读引用,扫描范围,扫描行数,未扫行数,首页上限,扫描页数,
                缓冲总行数,已汇总行数,汇总报文数,指纹,是否对齐,争用,状态,报告)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["时刻"], r["栏号"], r["读引用"], r["扫描范围"], r["扫描行数"],
             r["未扫行数"], 首页上限, r["扫描页数"], r["缓冲总行数"],
             r["已汇总缓冲"], r["汇总报文"], r["指纹"],
             1 if r["是否对齐"] else 0, 1 if r["争用"] else 0,
             "争用双态" if r["争用"] else ("完整" if r["是否对齐"] else "撕裂"),
             str({"组差异": r["组差异"], "缺行": r["缺行"][:10]})[:2000]),
        )
        _同步台灯(conn, r)
        conn.commit()
    finally:
        conn.close()
    return r
