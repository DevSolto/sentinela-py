"""Protocols and helper structures for NER integration."""
from __future__ import annotations

from typing import Iterable, Protocol

from .models import EntitySpan


class NEREngine(Protocol):
    """Interface for an entity recognition engine."""

    def analyze(self, text: str) -> Iterable[EntitySpan]:
        """Return entity spans detected in the provided text."""
