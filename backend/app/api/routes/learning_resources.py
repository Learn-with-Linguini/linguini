"""Read-only API for curated mission cheatsheets and character references."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.learning_resources import (
    character_references,
    get_character_reference,
    get_mission_cheat_sheet,
    mission_cheat_sheets,
)
from app.schemas.base import LanguageCode
from app.schemas.enums import ProficiencyLevel
from app.schemas.learning_resources import (
    CharacterReference,
    CharacterReferenceSummary,
    MissionCheatSheet,
    MissionCheatSheetSummary,
)
from app.schemas.tasks import ContentVersion, MissionId

router = APIRouter(prefix="/learning-resources", tags=["learning-resources"])


@router.get("/cheatsheets", response_model=list[MissionCheatSheetSummary])
def list_mission_cheat_sheets(
    language_code: Annotated[LanguageCode, Query(alias="languageCode")],
) -> list[MissionCheatSheetSummary]:
    return [
        MissionCheatSheetSummary.model_validate(cheat_sheet, from_attributes=True)
        for cheat_sheet in mission_cheat_sheets().values()
        if cheat_sheet.language_code.casefold() == language_code.casefold()
    ]


@router.get("/cheatsheets/{mission_id}", response_model=MissionCheatSheet)
def read_mission_cheat_sheet(
    mission_id: MissionId,
    language_code: Annotated[LanguageCode, Query(alias="languageCode")],
    practice_level: Annotated[ProficiencyLevel, Query(alias="practiceLevel")],
    content_version: Annotated[ContentVersion, Query(alias="contentVersion")] = 1,
) -> MissionCheatSheet:
    cheat_sheet = get_mission_cheat_sheet(
        mission_id, practice_level, content_version, language_code
    )
    if cheat_sheet is None:
        raise HTTPException(404, detail={
            "code": "cheatsheet_not_found",
            "message": "No cheatsheet is available for this mission and language.",
        })
    return cheat_sheet


@router.get(
    "/character-references", response_model=list[CharacterReferenceSummary]
)
def list_character_references(
    language_code: Annotated[
        LanguageCode | None, Query(alias="languageCode")
    ] = None,
) -> list[CharacterReferenceSummary]:
    return [
        CharacterReferenceSummary.model_validate(reference, from_attributes=True)
        for reference in character_references().values()
        if language_code is None
        or reference.language_code.casefold() == language_code.casefold()
    ]


@router.get(
    "/character-references/{reference_id}", response_model=CharacterReference
)
def read_character_reference(
    reference_id: str,
    content_version: Annotated[ContentVersion, Query(alias="contentVersion")] = 1,
) -> CharacterReference:
    reference = get_character_reference(reference_id, content_version)
    if reference is None:
        raise HTTPException(404, detail={
            "code": "character_reference_not_found",
            "message": "This character reference is not available.",
        })
    return reference
