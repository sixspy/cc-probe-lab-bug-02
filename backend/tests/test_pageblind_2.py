# -*- coding: utf-8 -*-
"""test_pageblind_2 —— 失败测乙。

命题：水位对账把未扫行当成“已扫齐套”，则红。
`目录.pageblind_齐套灯()` 旧实现只看装饰芯片是不是“对齐已亮”，
而芯片在播种时就被刷绿，真相位却是“尾页未扫”，于是齐套灯假齐套。

同时钉死题面允许的两种工程形态（二选一即可，这里把两条契约都写成可验收）：
- 审计账册：全量扫描指纹落账 + reject_refresh 拒未扫收口 + 读轨切 cutover_book；
- 双写两轨：首页快照进只读 archive_*，live_flag 立旗，现行读轨切 live_flag。
半修（只刷台灯）不得让 aligned 变真。
"""
from __future__ import annotations

import asyncio

from app.db import 连接
from app.services import 装载, 结栏, 目录, pageblind
from app.services import pageblind_cutover as cutover
from app.services import pageblind_dualwrite as dualwrite


def _灌满并结栏() -> None:
    报文 = []
    for i in range(20):
        报文.append({"报文编号": f"pb2-a-{i:02d}", "站点键": "站-河东", "指标键": "PM25",
                     "读数": 20.0, "观测时": f"2026-11-24T08:{i:02d}:00Z"})
    for i in range(5):
        报文.append({"报文编号": f"pb2-b-{i:02d}", "站点键": "站-北岭", "指标键": "PM25",
                     "读数": 30.0, "观测时": f"2026-11-24T09:0{i}:00Z"})
    assert 装载.装一批({"报文": 报文})["入栏"] == 25
    assert 结栏.结当前栏()["缓冲消耗"] == 25


def _撕尾页汇总组() -> None:
    conn = 连接()
    try:
        assert conn.execute("DELETE FROM 站点汇总账 WHERE 站点键='站-北岭'").rowcount == 1
        conn.commit()
    finally:
        conn.close()


def test_乙_齐套灯_新鲜库不得把尾页未扫当成齐套() -> None:
    灯 = 目录.pageblind_齐套灯()
    # 旧实现：齐套=True（只看绿芯片），对齐实值=False -> 假齐套
    assert 灯["齐套"] is False
    assert 灯["齐套"] == 灯["对齐实值"]
    assert "未扫行数" in 灯
    assert "扫描范围" in 灯


def test_乙_齐套灯_尾页盲区必须不齐套() -> None:
    _灌满并结栏()
    _撕尾页汇总组()
    灯 = 目录.pageblind_齐套灯()
    assert 灯["齐套"] is False
    assert 灯["对齐实值"] is False
    assert int(灯.get("未扫行数", 0)) == 0  # 全量游标扫尽，未扫计数为 0
    assert "全量" in str(灯["扫描范围"])


def test_乙_概览水位不把未扫当齐套() -> None:
    _灌满并结栏()
    _撕尾页汇总组()
    o = 目录.概览()
    assert "未扫行数" in o, "探栏台水位/卡片必须带未扫行数"
    assert "扫描范围" in o
    assert o.get("贯验齐套") is False
    assert o.get("灯亮绿") is False or o.get("灯色") != "green"


def test_乙_半修只刷台灯_读轨仍旧_aligned不得变真() -> None:
    out = pageblind.half_fix_display()
    assert out["half_fixed"] is True
    dash = pageblind.dashboard()
    assert dash["aligned"] is False
    assert dash["active_read"] == "old_track"
    # 半修之后齐套灯依旧不得齐套
    assert 目录.pageblind_齐套灯()["齐套"] is False


def test_工程形态甲_审计账册指纹拒回刷() -> None:
    out = cutover.append_cutover(1, "全量扫描指纹落审计账")
    assert out["active_read"] == "cutover_book"
    assert out["reject_refresh"] is True
    assert str(out["cutover_fp"]) not in ("", "stale-fp")
    dash = pageblind.dashboard()
    assert dash["active_read"] == "cutover_book"
    assert dash["reject_refresh"] is True
    assert dash["aligned"] is True


def test_工程形态乙_双写两轨首页归档读新旗() -> None:
    out = dualwrite.apply_dualwrite("首页快照只读归档，现行读全表游标")
    assert int(out["archive_count"]) >= 1
    assert bool(out["live_flag"]) is True
    assert out["active_read"] == "live_flag"
    dash = pageblind.dashboard()
    assert dash["active_read"] == "live_flag"
    assert int(dash["archive_count"]) >= 1
    assert bool(dash["live_flag"]) is True
    assert dash["aligned"] is True


def test_乙_http_齐套灯接口可达且带扫描范围() -> None:
    from app.main import app

    async def _hit():
        async with app.test_client() as c:
            resp = await c.get("/api/pageblind/齐套灯")
            return resp.status_code, await resp.get_json()

    status, data = asyncio.run(_hit())
    assert status == 200
    assert data and "齐套" in data and "扫描范围" in data
