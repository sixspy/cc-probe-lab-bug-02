"""贯验分页读轨审计。"""
from __future__ import annotations

from app.services import pageblind as core
from app.services import pageblind_cutover as cutover
from app.services import pageblind_dualwrite as dual


def audit_summary() -> dict:
    return {
        "title": "贯验分页审计",
        "core": core.dashboard(),
        "cutover": cutover.board(),
        "dualwrite": dual.dual_board(),
        "half": core.half_fix_display(),
    }
