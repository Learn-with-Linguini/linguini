"""Structured output returned for Linguini's Phase 1 I-Spy clues.

Re-export shim: the models now live in ``app.ai.features.ispy_clues.schemas``.
"""

from app.ai.features.ispy_clues.schemas import GeneratedISpyClue, ISpyClueResult

__all__ = ["GeneratedISpyClue", "ISpyClueResult"]
