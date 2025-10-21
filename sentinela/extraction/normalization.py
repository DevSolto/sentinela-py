"""Normalization helpers for the entity extraction pipeline."""
from __future__ import annotations

import re
import unicodedata
from typing import List, Sequence, Set, Tuple

from .models import NormalizedPersonName

_BOILERPLATE_PREFIXES = (
    "leia também",
    "leia ainda",
    "crédito:",
    "reportagem:",
    "foto:",
)

_HONORIFIC_PATTERNS = (
    r"\bdr\.?\b",
    r"\bdra\.?\b",
    r"\bdep\.?\b",
    r"\bdeputad[ao]a?\b",
    r"\bministr[ao]a?\b",
    r"\bpresidente\b",
    r"\bgovernador[ae]?\b",
    r"\bprefeit[ao]a?\b",
    r"\bvereador[ae]?\b",
    r"\bsenador[ae]?\b",
)

_STATE_NAMES = {
    "acre": "AC",
    "alagoas": "AL",
    "amapá": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceará": "CE",
    "distrito federal": "DF",
    "espírito santo": "ES",
    "goiás": "GO",
    "maranhão": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "pará": "PA",
    "paraíba": "PB",
    "paraná": "PR",
    "pernambuco": "PE",
    "piauí": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondônia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "são paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}

_STATE_ABBREVIATIONS = set(_STATE_NAMES.values())

_SENTENCE_REGEX = re.compile(r"[^.!?\n]+[.!?]?")
_CONNECTORS = {"da", "de", "dos", "das", "do", "e"}
_HYPHEN_CHARS = {"-", "‐", "‑", "‒", "–", "—", "―"}


def normalize_article_text(text: str) -> str:
    """Clean boilerplate snippets and normalise whitespace."""

    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(line.lower().startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _remove_titles(name: str) -> str:
    pattern = re.compile("|".join(_HONORIFIC_PATTERNS), re.IGNORECASE)
    without_titles = pattern.sub("", name)
    without_titles = re.sub(r"(?i)^ex[\s-]+", "", without_titles)
    without_titles = re.sub(r"^[^\wÀ-ÿ]+", "", without_titles)
    return without_titles


def _titlecase_word(word: str) -> str:
    if not word:
        return word
    lowered = word.lower()
    if word.isupper() and len(word) <= 3 and lowered not in _CONNECTORS:
        return word.upper()
    # Handle hyphenated names preserving accents
    parts = []
    for part in word.split("-"):
        part_lower = part.lower()
        if part_lower in _CONNECTORS:
            parts.append(part_lower.capitalize())
        else:
            parts.append(part.capitalize())
    return "-".join(parts)


def normalize_person_name(surface: str) -> NormalizedPersonName:
    """Return the canonical name and aliases for a surface form."""

    name = surface.strip()
    name = _remove_titles(name)
    name = re.sub(r"\s+", " ", name).strip()
    tokens = [_titlecase_word(token) for token in name.split(" ") if token]
    canonical = " ".join(tokens)
    aliases: Set[str] = set()
    if canonical and canonical != surface.strip():
        aliases.add(surface.strip())
    return NormalizedPersonName(canonical_name=canonical, aliases=aliases)


def find_sentence_containing(text: str, start: int, end: int) -> str:
    """Return the sentence that contains the character span."""

    for match in _SENTENCE_REGEX.finditer(text):
        if match.start() <= start < match.end():
            return match.group().strip()
    return text.strip()


def extract_state_mentions(text: str) -> Set[str]:
    """Identify Brazilian state abbreviations present in the text."""

    mentions: Set[str] = set()
    lowered = text.lower()
    for name, uf in _STATE_NAMES.items():
        if name in lowered:
            mentions.add(uf)
    for uf in _STATE_ABBREVIATIONS:
        pattern = rf"\b{uf}\b"
        if re.search(pattern, text):
            mentions.add(uf)
    return mentions


def _normalize_char_for_matching(char: str) -> Sequence[str]:
    """Return the characters used for matching along with accent stripping.

    The function lowers the input, removes combining marks and replaces the
    different hyphen characters by a single whitespace so that hyphenated names
    still respect word boundaries during matching.
    """

    if char in _HYPHEN_CHARS:
        return (" ",)
    if char == "\u00AD":  # soft hyphen
        return ()

    decomposed = unicodedata.normalize("NFKD", char)
    filtered = [c for c in decomposed if unicodedata.category(c) != "Mn"]
    if not filtered:
        return ()
    return tuple("".join(filtered).lower())


def normalize_text_with_offsets(text: str) -> Tuple[str, List[int]]:
    """Return a normalised version of ``text`` plus a map to original offsets.

    The resulting string is lower-cased, stripped from accents and with hyphen
    variants converted to regular whitespace. For each character in the
    normalised output, the returned offsets list stores the index of the
    originating character in ``text``. This is useful to run dictionary-based
    matching algorithms (such as the city matcher) while keeping the ability to
    translate matches back to the original text without losing positional
    information.
    """

    normalised_chars: List[str] = []
    offsets: List[int] = []
    for index, char in enumerate(text):
        replacements = _normalize_char_for_matching(char)
        for replacement in replacements:
            normalised_chars.append(replacement)
            offsets.append(index)
    return "".join(normalised_chars), offsets


__all__ = [
    "NormalizedPersonName",
    "extract_state_mentions",
    "find_sentence_containing",
    "normalize_article_text",
    "normalize_text_with_offsets",
    "normalize_person_name",
]
