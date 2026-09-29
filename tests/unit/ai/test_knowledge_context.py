"""Knowledge Context Builder v0.1: parsing, validation, card projection, assembly and digest.

Runs against the real corpus in docs/knowledge/sales/objections (read-only) and against mutated
copies in tmp_path. Assertions are structural; no full-corpus snapshot.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from closer_ai.ai.knowledge_context import (
    CARD_SECTIONS,
    CONCEPT_ORDER,
    CONTEXT_HEADER,
    NEGATIVE_SECTIONS,
    KnowledgeBaseError,
    KnowledgeUnit,
    build_knowledge_context,
    load_knowledge_units,
    render_card,
)

CORPUS = Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "sales" / "objections"


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "objections"
    shutil.copytree(CORPUS, root)
    return root


def _edit(root: Path, name: str, old: str, new: str) -> None:
    path = root / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture assumption broken: {old!r} not in {name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- corpus ---------------------------------------------------------------------------------


def test_real_corpus_loads_exactly_the_eight_units_in_canonical_order():
    units = load_knowledge_units(CORPUS)
    assert tuple(u.name for u in units) == CONCEPT_ORDER
    assert len({u.concept_id for u in units}) == 8


def test_order_does_not_depend_on_directory_listing(corpus: Path, tmp_path: Path):
    # recreate the files in reverse order: creation/listing order must not matter
    other = tmp_path / "reversed"
    other.mkdir()
    for name in reversed(CONCEPT_ORDER):
        shutil.copyfile(corpus / f"{name}.md", other / f"{name}.md")
    assert build_knowledge_context(other).text == build_knowledge_context(corpus).text


# --- parsing --------------------------------------------------------------------------------


def test_metadata_is_parsed():
    unit = load_knowledge_units(CORPUS)[0]
    assert unit.concept_id == "objection_category.PRICE_BUDGET"
    assert unit.version == "0.1"
    assert unit.status.startswith("PROVISIONAL")
    assert "SRC_HUBSPOT_OBJECTIONS" in unit.source_ids


def test_wrapped_metadata_value_is_joined(corpus: Path):
    path = corpus / "TIMING_PRIORITY.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("- status: ")
    end = text.index("\n", start)
    path.write_text(text[:start] + "- status: FIRST LINE\n  SECOND LINE" + text[end:], encoding="utf-8")
    unit = {u.name: u for u in load_knowledge_units(corpus)}["TIMING_PRIORITY"]
    assert unit.status == "FIRST LINE SECOND LINE"


def test_all_sections_parsed_and_multiline_preserved():
    unit = load_knowledge_units(CORPUS)[0]
    assert "Positive examples" in unit.sections  # parsed even if not projected (RAG-O4)
    assert unit.sections["Use when"].count("\n- ") >= 2
    assert not unit.sections["Definition"].startswith("\n")


def test_crlf_and_lf_corpora_produce_identical_context(corpus: Path):
    lf = build_knowledge_context(corpus)
    for path in corpus.glob("*.md"):
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    crlf = build_knowledge_context(corpus)
    assert crlf.text == lf.text and crlf.sha256 == lf.sha256
    assert "\r" not in crlf.text


# --- validation -----------------------------------------------------------------------------


def test_missing_metadata_fails(corpus: Path):
    _edit(corpus, "TRUST_RISK", "- version: 0.1\n", "")
    with pytest.raises(KnowledgeBaseError, match="missing metadata 'version'"):
        load_knowledge_units(corpus)


@pytest.mark.parametrize("heading", NEGATIVE_SECTIONS + ("Definition", "Sources"))
def test_missing_required_section_fails(corpus: Path, heading: str):
    _edit(corpus, "PRICE_BUDGET", f"## {heading}\n", "## Renamed\n")
    with pytest.raises(KnowledgeBaseError, match="missing or empty section"):
        load_knowledge_units(corpus)


def test_empty_required_section_fails(corpus: Path):
    path = corpus / "TIMING_PRIORITY.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("## Often confused with\n") + len("## Often confused with\n")
    end = text.index("## Positive examples")
    path.write_text(text[:start] + "\n" + text[end:], encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="'Often confused with'"):
        load_knowledge_units(corpus)


def test_duplicate_concept_id_fails(corpus: Path):
    # TRUST_RISK.md claiming to be PRICE_BUDGET would duplicate a concept
    _edit(corpus, "TRUST_RISK", "objection_category.TRUST_RISK", "objection_category.PRICE_BUDGET")
    with pytest.raises(KnowledgeBaseError, match="does not match file"):
        load_knowledge_units(corpus)


def test_duplicate_section_fails(corpus: Path):
    _edit(corpus, "TERMS_PROCESS", "## Open questions\n", "## Definition\n")
    with pytest.raises(KnowledgeBaseError, match="duplicate section"):
        load_knowledge_units(corpus)


def test_incomplete_corpus_fails(corpus: Path):
    (corpus / "TERMS_PROCESS.md").unlink()
    with pytest.raises(KnowledgeBaseError, match=r"missing=\['TERMS_PROCESS'\]"):
        load_knowledge_units(corpus)


def test_unexpected_file_is_not_treated_as_a_category(corpus: Path):
    shutil.copyfile(corpus / "PRICE_BUDGET.md", corpus / "STATUS_QUO.md")
    with pytest.raises(KnowledgeBaseError, match=r"unexpected=\['STATUS_QUO'\]"):
        load_knowledge_units(corpus)


def test_text_before_first_section_fails(corpus: Path):
    _edit(corpus, "NEED_VALUE_FIT", "# NEED_VALUE_FIT\n", "# NEED_VALUE_FIT\nstray text\n")
    with pytest.raises(KnowledgeBaseError, match="text before the first section"):
        load_knowledge_units(corpus)


# --- card rendering -------------------------------------------------------------------------


def _unit(**sections: str) -> KnowledgeUnit:
    return KnowledgeUnit(
        name="X",
        concept_id="objection_category.X",
        version="0.1",
        status="PROVISIONAL",
        source_strength="S4",
        source_ids=("SRC_A",),
        sections=sections,
    )


def test_render_card_exact_format_for_minimal_unit():
    unit = _unit(**{h: f"{h} body" for h in CARD_SECTIONS}, Sources="- `SRC_A` — S4")
    card = render_card(unit)
    expected = "\n\n".join(
        ["=== X ===", "concept_id: objection_category.X\nversion: 0.1\nstatus: PROVISIONAL"]
        + [f"### {h}\n{h} body" for h in CARD_SECTIONS]
    )
    assert card == expected


def test_card_carries_negative_knowledge_and_no_bibliography():
    for unit in load_knowledge_units(CORPUS):
        card = render_card(unit)
        headings = re.findall(r"^### (.+)$", card, flags=re.MULTILINE)
        assert tuple(headings) == CARD_SECTIONS
        assert set(NEGATIVE_SECTIONS) <= set(headings)
        assert "http" not in card
        assert unit.sections["Sources"] not in card
        assert unit.source_strength not in card
        for dropped in ("Positive examples", "Positive signals", "Sources", "Framework mappings"):
            assert f"### {dropped}" not in card


def test_projection_without_negative_sections_is_rejected():
    unit = load_knowledge_units(CORPUS)[0]
    with pytest.raises(KnowledgeBaseError, match="drops negative knowledge"):
        render_card(unit, ("Definition", "Use when", "Positive examples"))


def test_projection_can_add_positive_examples_without_parser_change():
    unit = load_knowledge_units(CORPUS)[0]
    card = render_card(unit, CARD_SECTIONS + ("Positive examples",))
    assert card.endswith(unit.sections["Positive examples"])


# --- context assembly -----------------------------------------------------------------------


def test_full_context_has_header_and_all_cards_in_order():
    ctx = build_knowledge_context(CORPUS)
    assert ctx.text.startswith(CONTEXT_HEADER + "\n\n")
    assert re.findall(r"^=== (\w+) ===$", ctx.text, flags=re.MULTILINE) == list(CONCEPT_ORDER)
    assert ctx.concept_ids == tuple(f"objection_category.{n}" for n in CONCEPT_ORDER)
    assert all(v == "0.1" for _, v in ctx.concept_versions)
    assert ctx.text.endswith("\n") and not ctx.text.endswith("\n\n")


def test_context_is_only_header_plus_cards():
    # nothing but the knowledge block: no transcript/deal/outcome slot is injected by the builder
    ctx = build_knowledge_context(CORPUS)
    rebuilt = "\n\n".join([CONTEXT_HEADER, *(render_card(u) for u in ctx.units)]) + "\n"
    assert ctx.text == rebuilt


# --- digest ---------------------------------------------------------------------------------


def test_digest_is_stable_and_well_formed(corpus: Path):
    a, b = build_knowledge_context(CORPUS), build_knowledge_context(corpus)
    assert a.sha256 == b.sha256
    assert re.fullmatch(r"[0-9a-f]{64}", a.sha256)


def test_material_change_changes_digest(corpus: Path):
    before = build_knowledge_context(corpus).sha256
    _edit(corpus, "PRICE_BUDGET", "## Do not use when\n\n", "## Do not use when\n\n- nova regra;\n")
    assert build_knowledge_context(corpus).sha256 != before


def test_change_outside_projection_keeps_digest(corpus: Path):
    before = build_knowledge_context(corpus).sha256
    _edit(corpus, "PRICE_BUDGET", "## Open questions\n\n", "## Open questions\n\n- outra dúvida\n")
    assert build_knowledge_context(corpus).sha256 == before


# --- explicit subset (future E3; caller-chosen, never ranked) -------------------------------


def test_subset_keeps_canonical_order():
    ctx = build_knowledge_context(CORPUS, concept_ids=["TERMS_PROCESS", "PRICE_BUDGET"])
    assert [u.name for u in ctx.units] == ["PRICE_BUDGET", "TERMS_PROCESS"]


def test_full_selection_equals_default():
    assert build_knowledge_context(CORPUS, list(CONCEPT_ORDER)) == build_knowledge_context(CORPUS)


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ([], "empty concept selection"),
        (["PRICE_BUDGET", "PRICE_BUDGET"], "duplicate concept"),
        (["STATUS_QUO"], "unknown concept"),
        (["objection_category.PRICE_BUDGET"], "unknown concept"),
    ],
)
def test_invalid_selection_fails(selection: list[str], message: str):
    with pytest.raises(KnowledgeBaseError, match=message):
        build_knowledge_context(CORPUS, concept_ids=selection)
