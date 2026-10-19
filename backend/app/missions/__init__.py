"""Registry of mission definitions: one TOML file per mission in ``definitions/``."""

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
    """``M02-A1.toml`` for content version 1, ``M02-A1-2.toml`` for later versions."""
    suffix = "" if mission.content_version == 1 else f"-{mission.content_version}"
    return f"{mission.mission_id}-{mission.practice_level}{suffix}.toml"


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
