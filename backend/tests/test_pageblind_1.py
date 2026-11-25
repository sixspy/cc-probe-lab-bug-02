# -*- coding: utf-8 -*-
"""test_pageblind_1 —— 失败测甲。

命题：尾页撕裂后对齐灯仍绿、且说明服务没有未扫计数，则实现为红。

复现路径（题面）：灌满超过首页（20 行）的夹具 -> 结栏 -> 人为撕尾页一行 -> 再贯验。
当前实现把“已汇总缓冲”计数 LIMIT 20 写死，且探栏台灯只认装饰芯片，
于是存在一个精确的假绿态：缓冲实有 25 行已汇总，撕掉尾页 5 行那一组汇总账后，
汇总报文数=20，被截断的扫描数也=20，旧贯验报“对齐”。
"""
from __future__ import annotations

from pathlib import Path

from app.db import 连接
from app.services import 装载, 结栏, 贯验, 说明, 目录, pageblind


def _超首页报文() -> list[dict]:
    """20 行河东 + 5 行北岭，共 25 行，超过首页 20。"""
    报文 = []
    for i in range(20):
        报文.append({
            "报文编号": f"pb1-a-{i:02d}",
            "站点键": "站-河东", "指标键": "PM25", "读数": 20.0,
            "观测时": f"2026-11-24T08:{i:02d}:00Z",
        })
    for i in range(5):
        报文.append({
            "报文编号": f"pb1-b-{i:02d}",
            "站点键": "站-北岭", "指标键": "PM25", "读数": 30.0,
            "观测时": f"2026-11-24T09:0{i}:00Z",
        })
    return 报文


def _灌满并结栏() -> None:
    报告 = 装载.装一批({"批次编号": "pb1", "报文": _超首页报文()})
    assert 报告["入栏"] == 25
    结 = 结栏.结当前栏()
    assert 结["缓冲消耗"] == 25


def _撕尾页汇总组() -> None:
    """撕掉尾页对应的北岭 5 行汇总账（一行），制造 25 vs 20 的盲区撕裂。"""
    conn = 连接()
    try:
        cur = conn.execute("DELETE FROM 站点汇总账 WHERE 站点键='站-北岭'")
        assert cur.rowcount == 1
        conn.commit()
    finally:
        conn.close()


def test_未撕时_超首页也必须全量对齐() -> None:
    """旧实现 20 != 25，未撕就报红，本身就是分页盲区症状。"""
    _灌满并结栏()
    r = 贯验.跑一次()
    assert r["是否对齐"] is True
    assert int(r["已汇总缓冲"]) == 25
    assert int(r["汇总报文"]) == 25
    # 必须交代扫描范围与未扫计数
    assert "未扫行数" in r, "贯验结果必须显式给出未扫行数"
    assert int(r["未扫行数"]) == 0
    assert "全量" in str(r["扫描范围"])


def test_甲_尾页撕汇总行后_对齐灯不得仍绿() -> None:
    _灌满并结栏()
    _撕尾页汇总组()
    r = 贯验.跑一次()
    # 全量读集必须看穿尾页撕裂：25 行缓冲 vs 20 报文汇总
    assert r["是否对齐"] is False, f"尾页撕裂竟仍判对齐：{r}"
    assert int(r["已汇总缓冲"]) == 25
    assert int(r["汇总报文"]) == 20
    # 对齐灯必须可区分：非绿
    assert r.get("灯色") in ("red", "amber") or r.get("对齐灯") in ("红", "黄"), r
    assert r.get("灯亮绿") is False


def test_甲_尾页撕缓冲行同样被全量扫描捕获() -> None:
    _灌满并结栏()
    conn = 连接()
    try:
        尾号 = conn.execute(
            "SELECT 报文编号 FROM 入栏缓冲 ORDER BY rowid DESC LIMIT 1"
        ).fetchone()["报文编号"]
        conn.execute("DELETE FROM 入栏缓冲 WHERE 报文编号=?", (尾号,))
        conn.commit()
    finally:
        conn.close()
    r = 贯验.跑一次()
    assert r["是否对齐"] is False
    assert int(r["未扫行数"]) == 0
    assert "全量" in str(r["扫描范围"])


def test_甲_说明仓情必须报未扫行数且不传假绿() -> None:
    _灌满并结栏()
    _撕尾页汇总组()
    info = 说明.仓情()
    assert "未扫行数" in info, "说明服务仓情必须报未扫行数"
    assert "扫描范围" in info
    # 仓情的对齐结论必须来自全量真相，而不是装饰芯片
    assert info.get("是否对齐") is False
    assert info.get("灯亮绿") is False or info.get("灯色") != "green"
    # pageblind 投影也不得在尾页撕裂时判 aligned
    dash = pageblind.dashboard()
    assert dash["aligned"] is False
    assert "未扫行数" in dash


def test_甲_五个页面源码均可见扫描范围() -> None:
    static_dir = Path(贯验.__file__).resolve().parents[1] / "static"
    for name in ["index.html", "入栏缓冲.html", "栏贯验.html",
                 "站点汇总账.html", "栏规.html"]:
        text = (static_dir / name).read_text(encoding="utf-8")
        assert "扫描范围" in text, f"{name} 必须页面可见扫描范围"
