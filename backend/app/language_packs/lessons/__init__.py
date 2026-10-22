"""Pack lesson implementations: one module per mission, each exposing ``MISSION``.

Every module follows the same layout (see ``m01.py``):

1. planning: ``plan_lesson`` plus one ``_plan_<level>`` per level, built with
   ``SpecBuilder``;
2. assembly: ``build_lesson`` plus one ``_build_<level>`` per level, built on
   ``LessonContext`` and the mission's existing task builder;
3. checks: ``check_inputs``, ``check_lesson`` and ``photo_reasons``;
4. ``MISSION = PackMission(...)``.

A mission listed here is pack-owned whenever language packs are enabled: it is
generated from the pack when ready and otherwise not offered, never built by its
legacy builder. Missions not listed keep their legacy implementation.
"""

from __future__ import annotations

from functools import cache
from importlib import import_module

from .base import PackMission

# Mission ID -> module in this package. Modules load on first use.
_MODULES = {
    "M01": "m01",
    "M02": "m02",
    "M03": "m03",
    "M04": "m04",
}
PACK_MISSION_IDS = frozenset(_MODULES)


@cache
def pack_mission(mission_id: str) -> PackMission:
    module_name = _MODULES.get(mission_id)
    if module_name is None:
        raise ValueError(f"mission {mission_id!r} has no pack lesson implementation")
    mission = import_module(f"{__name__}.{module_name}").MISSION
    if mission.mission_id != mission_id:
        raise RuntimeError(f"{module_name}.MISSION is registered as {mission.mission_id!r}")
    return mission


__all__ = ["PACK_MISSION_IDS", "PackMission", "pack_mission"]
