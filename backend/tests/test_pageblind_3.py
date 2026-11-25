# -*- coding: utf-8 -*-
"""test_pageblind_3 —— 争用失败测。

命题：贯验途中并发结栏会漏扫，产生“双态”，若此时仍亮对齐绿灯则红。

不变量（任何并发交错下都必须成立）：
1. 贯验/结栏并发不得抛出 database is locked 等异常；
2. 任何一次判“对齐”的贯验，都必须扫尽全量（未扫行数=0、扫描范围含全量），
   且自身计数相等——绝不允许漏扫带来的假绿；
3. 贯验结果必须带读引用/游标集与争用双态位，供调用方区分。
"""
from __future__ import annotations

import threading

from app.services import 装载, 结栏, 贯验


def test_争用_贯验结果必须是全量游标读集() -> None:
    r = 贯验.跑一次()
    for key in ("扫描范围", "未扫行数", "读引用", "争用", "双态"):
        assert key in r, f"贯验结果缺少争用/扫描契约字段：{key}"
    assert "全量" in str(r["扫描范围"])
    assert int(r["未扫行数"]) == 0
    assert str(r["读引用"]) in ("full_cursor", "cutover_book", "live_flag")


def test_争用_并发结栏不漏扫假绿不锁库() -> None:
    errors: list[str] = []
    false_greens: list[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(5)

    def _record(exc: Exception) -> None:
        with lock:
            errors.append(repr(exc))

    def closer(who: int) -> None:
        try:
            barrier.wait(timeout=10)
        except Exception:
            pass
        for k in range(6):
            try:
                报文 = [{
                    "报文编号": f"pb3-c{who}-{k}-{j}",
                    "站点键": "站-河东", "指标键": "PM25", "读数": 10 + j,
                    "观测时": f"2026-11-24T1{who}:{k:02d}:{j:02d}Z",
                } for j in range(3)]
                装载.装一批({"报文": 报文})
                结栏.结当前栏()
            except Exception as e:  # noqa: BLE001
                _record(e)

    def verifier() -> None:
        try:
            barrier.wait(timeout=10)
        except Exception:
            pass
        for _ in range(10):
            try:
                r = 贯验.跑一次()
                if r["是否对齐"]:
                    if (int(r.get("未扫行数", -1)) != 0
                            or "全量" not in str(r.get("扫描范围", ""))
                            or int(r["已汇总缓冲"]) != int(r["汇总报文"])):
                        with lock:
                            false_greens.append(r)
            except Exception as e:  # noqa: BLE001
                _record(e)

    threads = [threading.Thread(target=closer, args=(w,)) for w in range(2)]
    threads += [threading.Thread(target=verifier) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    for t in threads:
        assert not t.is_alive(), "并发线程超时未结束"

    assert not errors, f"并发期间出现异常（锁库/双态）：{errors[:3]}"
    assert not false_greens, f"漏扫假绿：{false_greens[:2]}"

    # 收束后再串行贯验一次，必须干净可读
    tail = 贯验.跑一次()
    assert "未扫行数" in tail
    assert int(tail["未扫行数"]) == 0
