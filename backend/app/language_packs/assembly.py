"""Word-tile assembly for approved language-pack sentences."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from pydantic import model_validator

from app.schemas.base import ApiModel, NonEmptyText

from .schema import ChunkJoin, SentenceChunk, WordSeparator
from .schema import join_pack_chunks as join_chunks

if TYPE_CHECKING:
    from .generation import ApprovedSentence


class Tile(ApiModel):
    tile_id: NonEmptyText
    text: NonEmptyText


class AssembledItem(ApiModel):
    tiles: list[Tile]
    answer_tile_ids: list[str]
    accepted_texts: list[str]
    word_separator: WordSeparator
    join_modes: list[ChunkJoin]

    @model_validator(mode="after")
    def validate_tiles(self):
        ids = [tile.tile_id for tile in self.tiles]
        if len(ids) != len(set(ids)):
            raise ValueError("tile IDs must be unique")
        if len(self.answer_tile_ids) != len(set(self.answer_tile_ids)):
            raise ValueError("an answer cannot reuse a tile ID")
        if set(self.answer_tile_ids) - set(ids):
            raise ValueError("answer references an unknown tile ID")
        if len(self.join_modes) != len(self.answer_tile_ids):
            raise ValueError("join modes must align with answer positions")
        return self


def assemble(
    approved: ApprovedSentence,
) -> AssembledItem:
    chunks = approved.candidate.chunks
    tiles = [
        Tile(
            tile_id=(
                f"{approved.candidate.slot_id}-{approved.candidate.spec_id or 'sentence'}"
                f"-tile-{index}"
            ),
            text=chunk.text,
        )
        for index, chunk in enumerate(chunks, 1)
    ]
    return AssembledItem(
        tiles=tiles,
        answer_tile_ids=[tile.tile_id for tile in tiles],
        accepted_texts=[approved.candidate.text],
        word_separator=approved.word_separator,
        join_modes=[chunk.join for chunk in chunks],
    )


def is_correct(item: AssembledItem, submitted_tile_ids: list[str]) -> bool:
    tile_texts = {tile.tile_id: tile.text for tile in item.tiles}
    available = Counter(tile.tile_id for tile in item.tiles)
    submitted = Counter(submitted_tile_ids)
    if submitted - available:
        return False
    chunks = [
        SentenceChunk(
            text=tile_texts[tile_id],
            join=item.join_modes[index] if index < len(item.join_modes) else "space",
        )
        for index, tile_id in enumerate(submitted_tile_ids)
    ]
    answer = join_chunks(chunks, item.word_separator)
    return answer in item.accepted_texts


def assemble_lesson(plan, approved: list[ApprovedSentence]) -> list[ApprovedSentence]:
    expected = [(slot.slot_id, spec.spec_id) for slot in plan.slots for spec in slot.specs]
    returned = [
        (item.candidate.slot_id, item.candidate.spec_id or item.candidate.slot_id)
        for item in approved
    ]
    if len(returned) != len(set(returned)):
        raise ValueError("duplicate approved sentence specs")
    if returned != expected:
        missing = set(expected) - set(returned)
        unknown = set(returned) - set(expected)
        if unknown:
            raise ValueError(f"unknown approved sentence specs: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing approved sentence specs: {sorted(missing)}")
        raise ValueError("approved sentence specs are not in planned order")
    return approved
