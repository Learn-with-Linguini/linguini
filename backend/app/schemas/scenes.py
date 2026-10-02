"""Static demo content; live session tasks use the separate task contracts."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.enums import PartOfSpeech
from app.schemas.media import PreloadedScene


class DemoSceneItem(ApiModel):
    id: NonEmptyText
    word: NonEmptyText
    translation: NonEmptyText
    word_class: PartOfSpeech
    gender: Literal["la", "el", "le", "l'"] | None
    marker: Annotated[int, Field(ge=1)]
    x: Annotated[float, Field(ge=0, le=100)]
    y: Annotated[float, Field(ge=0, le=100)]
    attributes: dict[str, str] = Field(default_factory=dict)
    example: str
    example_translation: str


class DemoSceneRelation(ApiModel):
    subject_item_id: NonEmptyText
    relation: NonEmptyText
    reference_item_id: NonEmptyText


class DemoSceneTask(ApiModel):
    id: NonEmptyText
    kind: Literal["word", "gender", "syntax", "phrase"]
    title: NonEmptyText
    summary: str
    xp: Annotated[int, Field(ge=0)]
    item_ids: list[str]
    note: str | None = None


class DemoSceneChoice(ApiModel):
    id: NonEmptyText
    label: NonEmptyText


class DemoSceneRound(ApiModel):
    id: NonEmptyText
    clue: NonEmptyText
    clue_translation: str
    answer_id: NonEmptyText
    choices: Annotated[list[DemoSceneChoice], Field(min_length=1)]
    encouragement: str


class DemoScenePrompt(ApiModel):
    id: NonEmptyText
    item_id: NonEmptyText
    suggestions: list[str]
    llm_guess: str
    feedback: str


class PreloadedSceneCatalogDetail(PreloadedScene):
    """Public catalog metadata; session activities and answers are not catalog data."""

    items: Annotated[list[DemoSceneItem], Field(min_length=1)]


class PreloadedSceneDetail(PreloadedScene):
    items: Annotated[list[DemoSceneItem], Field(min_length=1)]
    tasks: Annotated[list[DemoSceneTask], Field(min_length=1)]
    rounds: Annotated[list[DemoSceneRound], Field(min_length=1)]
    prompts: Annotated[list[DemoScenePrompt], Field(min_length=1)]
    relations: list[DemoSceneRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_references(self) -> "PreloadedSceneDetail":
        for rows in [self.items, self.tasks, self.rounds, self.prompts]:
            if len({row.id for row in rows}) != len(rows):
                raise ValueError("duplicate scene content ID")
        ids = {item.id for item in self.items}
        if any(not set(task.item_ids) <= ids for task in self.tasks):
            raise ValueError("unknown task item")
        for row in self.rounds:
            choice_ids = [choice.id for choice in row.choices]
            if (
                row.answer_id not in ids
                or row.answer_id not in choice_ids
                or len(set(choice_ids)) != len(choice_ids)
            ):
                raise ValueError("invalid round answer or choices")
        if any(prompt.item_id not in ids for prompt in self.prompts):
            raise ValueError("unknown prompt item")
        if any(
            relation.subject_item_id not in ids
            or relation.reference_item_id not in ids
            or relation.subject_item_id == relation.reference_item_id
            for relation in self.relations
        ):
            raise ValueError("invalid scene relation")
        return self
