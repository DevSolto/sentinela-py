from sentinela.extraction.normalization import (
    extract_state_mentions,
    find_sentence_containing,
    normalize_article_text,
    normalize_person_name,
)


def test_normalize_article_text_removes_boilerplate():
    text = "Leia também: algo\nCorpo da matéria\nCrédito: foto"
    assert normalize_article_text(text) == "Corpo da matéria"


def test_normalize_person_name_removes_titles_and_titlecases():
    result = normalize_person_name("Dr. JOÃO DA SILVA")
    assert result.canonical_name == "João Da Silva"
    assert "Dr. JOÃO DA SILVA" in result.aliases


def test_find_sentence_containing_returns_expected_sentence():
    text = "Primeira frase. Segunda frase com João." \
        " Terceira frase."
    sentence = find_sentence_containing(text, text.index("João"), text.index("João") + 4)
    assert sentence == "Segunda frase com João."


def test_extract_state_mentions_handles_names_and_abbreviations():
    text = "O governador de Pernambuco visitou Recife - PE."
    mentions = extract_state_mentions(text)
    assert mentions == {"PE"}
