"""Word-tile assembly for approved language-pack sentences."""

from __future__ import annotations

from typing import TYPE_CHECKING

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


def assemble(
    approved: ApprovedSentence,
) -> AssembledItem:
    chunks = approved.candidate.chunks
    tiles = [
        Tile(tile_id=f"{approved.candidate.slot_id}-tile-{index}", text=chunk.text)
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
    if any(tile_id not in tile_texts for tile_id in submitted_tile_ids):
        return False
    chunks = [
        SentenceChunk(
            text=tile_texts[tile_id],
            join=item.join_modes[index]
            if index < len(item.join_modes)
            else "space",
        )
        for index, tile_id in enumerate(submitted_tile_ids)
    ]
    answer = join_chunks(chunks, item.word_separator)
    return answer in item.accepted_texts
