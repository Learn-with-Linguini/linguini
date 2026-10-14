"""Registry of versioned mission definitions stored as TOML in ``definitions/``.

A definition is immutable once tasks reference it: change content by adding a file
with the next ``content_version`` instead of editing a published one.
"""

import tomllib
from functools import cache
from pathlib import Path

from pydantic import ValidationError

from app.schemas.enums import ProficiencyLevel
from app.schemas.missions import MissionDefinition

DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class MissionConfigurationError(ValueError):
    pass


def definition_file_name(mission: MissionDefinition) -> str:
    return f"{mission.mission_id}-{mission.practice_level}.v{mission.content_version}.toml"


def load_mission_file(path: Path) -> MissionDefinition:
    try:
        mission = MissionDefinition.model_validate(tomllib.loads(path.read_text("utf-8")))
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise MissionConfigurationError(f"Invalid mission definition {path.name}: {exc}") from None
    if path.name != definition_file_name(mission):
        raise MissionConfigurationError(
            f"{path.name} must be named {definition_file_name(mission)}"
        )
    return mission


def load_missions(directory: Path) -> dict[tuple[str, ProficiencyLevel, int], MissionDefinition]:
    missions = {}
    for path in sorted(directory.glob("*.toml")):
        mission = load_mission_file(path)
        missions[mission.key] = mission
    return missions


@cache
def mission_definitions() -> dict[tuple[str, ProficiencyLevel, int], MissionDefinition]:
    return load_missions(DEFINITIONS_DIR)


def get_mission(
    mission_id: str, practice_level: ProficiencyLevel | str, content_version: int
) -> MissionDefinition | None:
    return mission_definitions().get(
        (mission_id, ProficiencyLevel(practice_level), content_version)
    )
