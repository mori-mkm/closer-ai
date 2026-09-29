"""Knowledge Context Builder v0.1: Sales Knowledge Base Markdown -> deterministic context block.

See docs/ai/KNOWLEDGE_CONTEXT_BUILDER_V0_1.md and
docs/ai/SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md (E2: full-context knowledge augmentation).

This is plumbing, not retrieval: the caller decides which concepts go in (all by default); nothing
here ranks, scores or selects. The produced text is *external knowledge*: it defines categories and
is never evidence that anything happened in a call (only transcript segment_ids are).

Design decisions worth knowing:

- The corpus format is owned by this repo (docs/knowledge/sales/README.md), so parsing is a strict
  line scan over `# NAME`, `## Heading` and `- key: value` metadata lines, not a Markdown parser.
  Anything unexpected fails loudly instead of producing a partial card.
- Files are read with universal newlines, so a CRLF checkout (Windows, git autocrlf) and an LF
  checkout produce byte-identical context and the same digest. Section bodies keep their inner text
  verbatim; only leading/trailing blank lines are dropped.
- `CONCEPT_ORDER` is the CIT-O1 annotation taxonomy order (taxonomy proposal / guideline v0.1).
  It is deliberately *not* derived from `closer_ai.domain.objection.ObjectionCategory`: the
  annotation label set is not the domain enum.
- `CARD_SECTIONS` is the default card projection. Positive examples / positive signals are parsed
  but not projected by default: whether cards should carry them is an open decision (RAG-O4), so a
  future eval can pass another `sections` tuple without touching the parser. Every projection must
  keep `NEGATIVE_SECTIONS` — a card is never positive-only.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

CONCEPT_ORDER: tuple[str, ...] = (
    "PRICE_BUDGET",
    "TIMING_PRIORITY",
    "NEED_VALUE_FIT",
    "AUTHORITY_INTERNAL_BUY_IN",
    "TRUST_RISK",
    "COMPETITION_EXISTING_SOLUTION",
    "IMPLEMENTATION_INTEGRATION",
    "TERMS_PROCESS",
)

NEGATIVE_SECTIONS: tuple[str, ...] = (
    "Do not use when",
    "Negative / falsifying signals",
    "Often confused with",
    "Ambiguous examples",
    "Observed vs inferred risks",
)

CARD_SECTIONS: tuple[str, ...] = (
    "Definition",
    "Use when",
    "Do not use when",
    "Minimum transcript evidence",
    "Negative / falsifying signals",
    "Often confused with",
    "Ambiguous examples",
    "Observed vs inferred risks",
)

_METADATA_KEYS: tuple[str, ...] = ("concept_id", "version", "status", "source_strength")
_REQUIRED_SECTIONS: tuple[str, ...] = ("Metadata", *CARD_SECTIONS, "Sources")
_CONCEPT_ID_PREFIX = "objection_category."
_SOURCE_ID = re.compile(r"\bSRC_[A-Z0-9_]+\b")
_METADATA_LINE = re.compile(r"^- ([a-z_]+): (.+)$")

CONTEXT_HEADER = (
    "EXTERNAL KNOWLEDGE — NOT FROM THIS CALL\n"
    "\n"
    "The following content defines provisional annotation categories (not domain values).\n"
    "It is not evidence that anything occurred in the call.\n"
    "Only transcript segment_ids can support occurrence.\n"
    "Examples below are synthetic and did not happen in this call."
)


class KnowledgeBaseError(ValueError):
    """The knowledge base is malformed or incomplete; no context is built."""


@dataclass(frozen=True)
class KnowledgeUnit:
    name: str  # e.g. "PRICE_BUDGET" — file stem, title and concept_id suffix all agree
    concept_id: str  # e.g. "objection_category.PRICE_BUDGET"
    version: str
    status: str
    source_strength: str  # run provenance only, never rendered into the card
    source_ids: tuple[str, ...]  # run provenance only, never rendered into the card
    sections: Mapping[str, str]  # every `## Heading` body in the file, read-only


@dataclass(frozen=True)
class KnowledgeContext:
    text: str
    sha256: str  # hex digest of text.encode("utf-8")
    units: tuple[KnowledgeUnit, ...]  # in the order rendered; carries provenance for the run

    @property
    def concept_ids(self) -> tuple[str, ...]:
        return tuple(u.concept_id for u in self.units)

    @property
    def concept_versions(self) -> tuple[tuple[str, str], ...]:
        return tuple((u.concept_id, u.version) for u in self.units)


def _parse_unit(path: Path) -> KnowledgeUnit:
    lines = path.read_text(encoding="utf-8").split("\n")  # universal newlines: CRLF -> "\n"
    name = path.stem
    if not lines or lines[0] != f"# {name}":
        raise KnowledgeBaseError(f"{path.name}: first line must be '# {name}'")

    bodies: dict[str, list[str]] = {}
    current: list[str] | None = None
    for i, line in enumerate(lines[1:], start=2):
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading in bodies:
                raise KnowledgeBaseError(f"{path.name}:{i}: duplicate section '{heading}'")
            current = bodies[heading] = []
        elif line.startswith("# "):
            raise KnowledgeBaseError(f"{path.name}:{i}: unexpected top-level heading")
        elif current is not None:
            current.append(line)
        elif line.strip():
            raise KnowledgeBaseError(f"{path.name}:{i}: text before the first section")
    sections = {h: "\n".join(body).strip("\n") for h, body in bodies.items()}

    for heading in _REQUIRED_SECTIONS:
        if not sections.get(heading, "").strip():
            raise KnowledgeBaseError(f"{path.name}: missing or empty section '{heading}'")

    metadata: dict[str, str] = {}
    last_key: str | None = None
    for line in sections["Metadata"].split("\n"):
        match = _METADATA_LINE.match(line)
        if match:
            last_key = match.group(1)
            metadata[last_key] = match.group(2).strip()
        elif line.startswith("  ") and last_key is not None:  # wrapped value
            metadata[last_key] += " " + line.strip()
        elif line.strip():
            raise KnowledgeBaseError(f"{path.name}: unparseable metadata line {line!r}")
    for key in _METADATA_KEYS:
        if not metadata.get(key):
            raise KnowledgeBaseError(f"{path.name}: missing metadata '{key}'")

    concept_id = metadata["concept_id"].strip("`")
    if concept_id != _CONCEPT_ID_PREFIX + name:
        raise KnowledgeBaseError(
            f"{path.name}: concept_id {concept_id!r} does not match file '{_CONCEPT_ID_PREFIX}{name}'"
        )
    source_ids = tuple(dict.fromkeys(_SOURCE_ID.findall(sections["Sources"])))
    if not source_ids:
        raise KnowledgeBaseError(f"{path.name}: no SRC_* id in 'Sources'")

    return KnowledgeUnit(
        name=name,
        concept_id=concept_id,
        version=metadata["version"],
        status=metadata["status"],
        source_strength=metadata["source_strength"],
        source_ids=source_ids,
        sections=MappingProxyType(sections),
    )


def load_knowledge_units(knowledge_root: Path) -> tuple[KnowledgeUnit, ...]:
    """Parse and validate every unit under `knowledge_root`, returned in `CONCEPT_ORDER`.

    The directory must contain exactly one `<NAME>.md` per concept in `CONCEPT_ORDER` and nothing
    else ending in `.md`: a missing concept or an unknown file is an error, never skipped.
    """
    files = {p.stem: p for p in Path(knowledge_root).glob("*.md")}
    unexpected = sorted(set(files) - set(CONCEPT_ORDER))
    missing = [name for name in CONCEPT_ORDER if name not in files]
    if unexpected or missing:
        raise KnowledgeBaseError(f"corpus mismatch: missing={missing} unexpected={unexpected}")
    return tuple(_parse_unit(files[name]) for name in CONCEPT_ORDER)


def render_card(unit: KnowledgeUnit, sections: Sequence[str] = CARD_SECTIONS) -> str:
    """Render one classification card. Only card text; no sources, URLs or source strength."""
    lacking = [s for s in NEGATIVE_SECTIONS if s not in sections]
    if lacking:
        raise KnowledgeBaseError(f"card projection drops negative knowledge: {lacking}")
    parts = [
        f"=== {unit.name} ===",
        f"concept_id: {unit.concept_id}\nversion: {unit.version}\nstatus: {unit.status}",
    ]
    for heading in sections:
        if heading not in unit.sections:
            raise KnowledgeBaseError(f"{unit.name}: no section '{heading}' to project")
        parts.append(f"### {heading}\n{unit.sections[heading]}")
    return "\n\n".join(parts)


def build_knowledge_context(
    knowledge_root: Path,
    concept_ids: Sequence[str] | None = None,
    sections: Sequence[str] = CARD_SECTIONS,
) -> KnowledgeContext:
    """Assemble the EXTERNAL KNOWLEDGE block and its sha256.

    `concept_ids=None` means all concepts (E2). An explicit sequence of names (e.g.
    `["PRICE_BUDGET"]`) selects that subset, rendered in canonical order; an empty, duplicated or
    unknown selection is an error. The builder never chooses concepts itself.
    """
    units = load_knowledge_units(knowledge_root)
    if concept_ids is not None:
        requested = list(concept_ids)
        if not requested:
            raise KnowledgeBaseError("empty concept selection (use None for all concepts)")
        if len(set(requested)) != len(requested):
            raise KnowledgeBaseError(f"duplicate concept in selection: {requested}")
        unknown = sorted(set(requested) - set(CONCEPT_ORDER))
        if unknown:
            raise KnowledgeBaseError(f"unknown concept(s): {unknown}")
        units = tuple(u for u in units if u.name in requested)

    text = "\n\n".join([CONTEXT_HEADER, *(render_card(u, sections) for u in units)]) + "\n"
    return KnowledgeContext(
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        units=units,
    )
