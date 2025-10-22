"""Motor de matching para identificar menções a cidades em textos."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping, MutableMapping, Sequence

from sentinela.extraction.normalization import normalize_text_with_offsets

_WORD_CHAR = set("abcdefghijklmnopqrstuvwxyz0123456789")


@dataclass(frozen=True, slots=True)
class CityMatch:
    """Resultado de uma correspondência de cidade."""

    city_id: str | None
    name: str
    uf: str | None
    surface: str
    start: int
    end: int
    method: str
    score: float


@dataclass(frozen=True, slots=True)
class _CityKeyword:
    key: str
    length: int
    city_id: str
    name: str
    uf: str


class _AutomatonNode:
    __slots__ = ("children", "fail", "outputs")

    def __init__(self) -> None:
        self.children: MutableMapping[str, _AutomatonNode] = {}
        self.fail: _AutomatonNode | None = None
        self.outputs: list[_CityKeyword] = []


class CityMatcher:
    """Identifica menções a municípios usando automato estilo FlashText.

    Optamos por uma implementação própria do automato tipo FlashText para
    evitar dependências binárias como ``pyahocorasick`` (que traria um custo de
    build em ambientes sem compilador) mantendo a eficiência linear para busca
    de múltiplas palavras-chave.
    """

    def __init__(self, catalog: Sequence[Mapping[str, Any]] | Mapping[str, Any]):
        if isinstance(catalog, Mapping):
            entries = catalog.get("data", [])
        else:
            entries = catalog

        self._root = _AutomatonNode()
        for entry in entries:
            ibge_id = entry.get("ibge_id")
            canonical_name = entry.get("name")
            if not ibge_id or not canonical_name:
                continue

            city_id = str(ibge_id)
            uf = entry.get("uf") or ""
            variants: Iterable[str] = [canonical_name]
            alt_names = entry.get("alt_names")
            if isinstance(alt_names, Iterable) and not isinstance(alt_names, (str, bytes)):
                variants = list({*variants, *map(str, alt_names)})

            for variant in variants:
                normalised, _ = normalize_text_with_offsets(variant)
                key = normalised.strip()
                if not key:
                    continue
                keyword = _CityKeyword(
                    key=key,
                    length=len(key),
                    city_id=city_id or None,
                    name=canonical_name,
                    uf=uf or None,
                )
                self._insert_keyword(keyword)
        self._build_fail_transitions()

    def _insert_keyword(self, keyword: _CityKeyword) -> None:
        node = self._root
        for char in keyword.key:
            node = node.children.setdefault(char, _AutomatonNode())
        node.outputs.append(keyword)

    def _build_fail_transitions(self) -> None:
        queue: deque[_AutomatonNode] = deque()
        for child in self._root.children.values():
            child.fail = self._root
            queue.append(child)

        while queue:
            node = queue.popleft()
            for char, child in node.children.items():
                queue.append(child)
                fail_node = node.fail
                while fail_node is not None and char not in fail_node.children:
                    fail_node = fail_node.fail
                child.fail = fail_node.children[char] if fail_node and char in fail_node.children else self._root
                child.outputs.extend(child.fail.outputs if child.fail is not None else [])

    @staticmethod
    def _is_word_char(char: str) -> bool:
        return char in _WORD_CHAR

    @staticmethod
    def _boundary_ok(text: str, start: int, end: int) -> bool:
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        return (not before or not CityMatcher._is_word_char(before)) and (
            not after or not CityMatcher._is_word_char(after)
        )

    def _iter_automaton_matches(
        self, text: str
    ) -> Iterator[CityMatch]:
        normalised_text, offsets = normalize_text_with_offsets(text)
        node = self._root
        for index, char in enumerate(normalised_text):
            while node is not None and char not in node.children:
                node = node.fail
            if node is None:
                node = self._root
                continue
            node = node.children.get(char, self._root)
            if node is None:
                node = self._root
                continue
            for keyword in node.outputs:
                start = index - keyword.length + 1
                end = index + 1
                if start < 0:
                    continue
                if not self._boundary_ok(normalised_text, start, end):
                    continue
                orig_start = offsets[start]
                orig_end = offsets[end - 1] + 1
                surface = text[orig_start:orig_end]
                yield CityMatch(
                    city_id=keyword.city_id,
                    name=keyword.name,
                    uf=keyword.uf,
                    surface=surface,
                    start=orig_start,
                    end=orig_end,
                    method="automaton",
                    score=1.0,
                )

    def find_matches(self, text: str) -> list[CityMatch]:
        matches = list(self._iter_automaton_matches(text))
        matches.sort(key=lambda item: (item.start, item.end))
        return matches


__all__ = ["CityMatcher", "CityMatch"]
