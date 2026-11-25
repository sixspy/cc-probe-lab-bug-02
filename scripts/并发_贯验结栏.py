#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并发脚本：贯验 × 结栏 争用不变量 + 尾页撕裂可区分性联演。

命题（probe-bug-02 贯验分页盲区）：
1. 贯验全量游标读集与结栏并发时，不得抛 database is locked；
2. 任何判“对齐/绿”的贯验都必须扫尽全量（未扫行数=0、扫描范围含“全量”），
   且 已汇总缓冲 == 汇总报文，绝不允许漏扫假绿；
3. 收束后再贯验一次必须干净（未扫行数=0）；
4. 尾页人为撕一行后，对齐灯必须由绿转红，且显式给出扫描范围/未扫计数；
5. 审计账册形态必须落下全量指纹并把读轨切到 cutover_book。

退出码：0 全部不变量成立；1 出现锁库/假绿/超时/灯不可区分等失败。

用法：
    python3 scripts/并发_贯验结栏.py
"""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

# --- 把 backend/ 放进 sys.path，使脚本在任意 cwd 下可直接运行 ---
_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_BACKEND))

# --- 与 tests/conftest.py 同构：脚本自隔离临时库，不碰仓库/真实数据 ---
_TMP = Path(tempfile.mkdtemp(prefix="pb3-script-"))
import app.db as db  # noqa: E402

db.数据目录 = _TMP
db.库路径 = _TMP / "探栏.db"
_FIX = _BACKEND / "tests" / "fixtures"
if not _FIX.exists():
    _FIX = _ROOT / "fixtures"
db.夹具目录 = _FIX

from app import seed  # noqa: E402
from app.db import 连接  # noqa: E402
from app.services import 装载, 结栏, 贯验, pageblind  # noqa: E402
from app.services import pageblind_cutover as cutover  # noqa: E402


def main() -> int:
    seed.初始化库()
    failures: list[str] = []
    errors: list[str] = []
    false_greens: list[dict] = []
    lock = threading.Lock()

    def record_error(e: Exception) -> None:
        with lock:
            errors.append(repr(e))

    barrier = threading.Barrier(5)

    def closer(who: int) -> None:
        try:
            barrier.wait(timeout=10)
        except Exception:
            pass
        for k in range(6):
            try:
                报文 = [{
                    "报文编号": f"script-c{who}-{k}-{j}",
                    "站点键": "站-河东", "指标键": "PM25", "读数": 10 + j,
                    "观测时": f"2026-11-25T1{who}:{k:02d}:{j:02d}Z",
                } for j in range(3)]
                装载.装一批({"报文": 报文})
                结栏.结当前栏()
            except Exception as e:  # noqa: BLE001
                record_error(e)

    def verifier() -> None:
        try:
            barrier.wait(timeout=10)
        except Exception:
            pass
        for _ in range(10):
            try:
                r = 贯验.跑一次()
                if r["是否对齐"] and (
                    int(r.get("未扫行数", -1)) != 0
                    or "全量" not in str(r.get("扫描范围", ""))
                    or int(r["已汇总缓冲"]) != int(r["汇总报文"])
                ):
                    with lock:
                        false_greens.append({
                            k: r.get(k) for k in
                            ("是否对齐", "未扫行数", "扫描范围",
                             "已汇总缓冲", "汇总报文", "争用")
                        })
            except Exception as e:  # noqa: BLE001
                record_error(e)

    threads = [threading.Thread(target=closer, args=(w,), name=f"closer-{w}")
               for w in range(2)]
    threads += [threading.Thread(target=verifier, name=f"verifier-{i}")
                for i in range(3)]
    print(f"[并发] 启动 2 结栏 + 3 贯验（barrier=5），临时库 {_TMP}")
    for t in threads:
        t.start()
    timed_out = False
    for t in threads:
        t.join(timeout=90)
        if t.is_alive():
            timed_out = True
    if timed_out:
        failures.append("并发线程 90s 超时未结束")

    print(f"[并发] 异常 {len(errors)} 条；漏扫假绿 {len(false_greens)} 次")
    for e in errors[:5]:
        print("  ERROR:", e)
    for g in false_greens[:3]:
        print("  FALSE-GREEN:", g)
    if errors:
        failures.append(f"并发期间出现异常（锁库/双态）：{errors[:3]}")
    if false_greens:
        failures.append(f"出现漏扫假绿：{false_greens[:2]}")

    tail = 贯验.跑一次()
    print(f"[收束] 扫描范围={tail['扫描范围']} 未扫行数={tail['未扫行数']} "
          f"已汇总缓冲={tail['已汇总缓冲']} 汇总报文={tail['汇总报文']} "
          f"对齐={tail['是否对齐']} 灯={tail['灯色']} 争用={tail['争用']}")
    if int(tail["未扫行数"]) != 0:
        failures.append("收束后仍有未扫行数")

    # --- 尾页撕裂可区分性：另起一个干净库，灌满 >20 -> 结栏 -> 撕尾页汇总组 -> 再贯验 ---
    tear_tmp = Path(tempfile.mkdtemp(prefix="pb3-tear-"))
    db.库路径 = tear_tmp / "探栏.db"
    seed.初始化库()
    报文 = []
    for i in range(20):
        报文.append({"报文编号": f"rip-a-{i:02d}", "站点键": "站-河东",
                     "指标键": "PM25", "读数": 20.0,
                     "观测时": f"2026-11-25T08:{i:02d}:00Z"})
    for i in range(5):
        报文.append({"报文编号": f"rip-b-{i:02d}", "站点键": "站-北岭",
                     "指标键": "PM25", "读数": 30.0,
                     "观测时": f"2026-11-25T09:0{i}:00Z"})
    n = 装载.装一批({"批次编号": "rip", "报文": 报文})["入栏"]
    consumed = 结栏.结当前栏()["缓冲消耗"]
    healthy = 贯验.跑一次()
    conn = 连接()
    try:
        cur = conn.execute("DELETE FROM 站点汇总账 WHERE 站点键='站-北岭'")
        torn_rows = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    torn = 贯验.跑一次()
    dash = pageblind.dashboard()
    print(f"[撕裂] 入栏={n} 结栏消耗={consumed} 删除尾页汇总组行={torn_rows}")
    print(f"[撕裂] 健康态：对齐={healthy['是否对齐']} 灯={healthy['灯色']} "
          f"绿={healthy['灯亮绿']} 计数={healthy['已汇总缓冲']}/{healthy['汇总报文']}")
    print(f"[撕裂] 撕后态：对齐={torn['是否对齐']} 灯={torn['灯色']} "
          f"绿={torn['灯亮绿']} 计数={torn['已汇总缓冲']}/{torn['汇总报文']} "
          f"未扫={torn['未扫行数']} 范围={torn['扫描范围']}")
    print(f"[台灯] aligned={dash['aligned']} 灯色={dash['灯色']} "
          f"齐套={dash['齐套']} mismatch={dash['panel_pack_mismatch']}")

    if n != 25 or consumed != 25:
        failures.append(f"夹具未灌满 25 行：入栏={n} 消耗={consumed}")
    if healthy["是否对齐"] is not True or healthy["灯亮绿"] is not True:
        failures.append("健康超首页数据未亮绿灯（假红）")
    if torn_rows != 1:
        failures.append(f"尾页撕裂夹具未命中唯一汇总组：rowcount={torn_rows}")
    if torn["是否对齐"] is not False or torn["灯亮绿"] is not False:
        failures.append("尾页撕裂后仍判对齐/亮绿（假绿未修）")
    if torn["灯色"] not in ("red", "amber"):
        failures.append(f"尾页撕裂后灯色不可区分：{torn['灯色']}")
    if int(torn["已汇总缓冲"]) != 25 or int(torn["汇总报文"]) != 20:
        failures.append("全量扫描未看穿 25 vs 20 撕裂")
    if dash["aligned"] is not False or dash["灯亮绿"] is not False:
        failures.append("pageblind 台灯在撕裂后仍 aligned/绿")

    # --- 审计账册形态：在一个干净健康库上验证 全量指纹落账 + 读轨切换 + 拒回刷 + 绿灯 ---
    book_tmp = Path(tempfile.mkdtemp(prefix="pb3-book-"))
    db.库路径 = book_tmp / "探栏.db"
    seed.初始化库()
    healthy_msgs = [{
        "报文编号": f"book-{i:02d}", "站点键": "站-河东", "指标键": "PM25",
        "读数": 20.0, "观测时": f"2026-11-25T10:{i:02d}:00Z",
    } for i in range(25)]
    装载.装一批({"批次编号": "book", "报文": healthy_msgs})
    结栏.结当前栏()
    out = cutover.append_cutover(1, "并发脚本收口：全量扫描指纹落审计账")
    book_dash = pageblind.dashboard()
    print(f"[账册] active_read={out['active_read']} reject={out['reject_refresh']} "
          f"fp={out['cutover_fp']} aligned={out['aligned']} 台灯齐套={book_dash['齐套']}")
    if out["active_read"] != "cutover_book" or out["reject_refresh"] is not True:
        failures.append("审计账册读轨/拒回刷契约未成立")
    if not out["cutover_fp"] or out["cutover_fp"] == "stale-fp":
        failures.append("审计账册缺少耐久全量指纹")
    if out["aligned"] is not True or book_dash["aligned"] is not True:
        failures.append("健康全量账册收口后未亮齐套绿灯")

    print("-" * 60)
    if failures:
        print("结论：失败 ✗")
        for f in failures:
            print(" -", f)
        return 1
    print("结论：全部不变量成立 ✓（无锁库 / 无漏扫假绿 / 尾页撕裂灯可区分 / 账册落指纹）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
