"""Case format for the scene-translation evaluation dataset.

A case is the input payload the translator receives, plus metadata. It carries
no expected answers: those come from ``lexicon.py``, keyed on the English
source word. Keeping them apart means a correction to "shelf" is made once
rather than in every case that happens to mention a shelf.

The payload mirrors what ``SceneTranslator.translate`` is given in production,
including the ``targetLanguage``/``sceneTitle`` camelCase spelling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .lexicon import SUPPORTED_LANGUAGES


class CaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Term(CaseModel):
    key: str
    source: str


class TranslationCase(CaseModel):
    case_id: str
    target_language: str
    scene_title: str
    scene_summary: str
    objects: list[Term]
    attributes: list[Term] = []
    relationships: list[Term] = []
    tags: list[str] = []
    notes: str | None = None

    def payload(self) -> dict[str, Any]:
        """The exact request body the translator is called with."""
        return {
            "targetLanguage": self.target_language,
            "sceneTitle": self.scene_title,
            "sceneSummary": self.scene_summary,
            "objects": [term.model_dump() for term in self.objects],
            "attributes": [term.model_dump() for term in self.attributes],
            "relationships": [term.model_dump() for term in self.relationships],
        }


def load_cases(cases_dir: Path) -> list[TranslationCase]:
    cases = [
        TranslationCase.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cases_dir.glob("*.json"))
    ]
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise ValueError(f"duplicate case_id {case.case_id!r}")
        if case.target_language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"{case.case_id}: unsupported language {case.target_language!r}"
            )
        seen.add(case.case_id)
    return cases


def dump_case(case: TranslationCase) -> str:
    return json.dumps(case.model_dump(exclude_none=True), indent=2, ensure_ascii=False) + "\n"
