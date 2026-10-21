"""Demo / pilot CLI: transcript .txt -> PostCallIntelligence JSON + Markdown, via local Ollama.

    python -m closer_ai.demo.analyze_call examples/calls/authority_partner.txt
    python -m closer_ai.demo.analyze_call examples/calls/            # batch: every *.txt, sequential
    python -m closer_ai.demo.analyze_call <private_dir> --out-dir <private_out_dir> \\
        --roles "Renato=lead,Ana=closer" --continue-on-error         # real-call pilot

Transcript format (one utterance per line; blank lines and lines starting with '#' are ignored):

    closer: Bom dia, tudo bem?
    lead: Tudo. Preciso falar com meu sócio antes.

Speaker labels are `closer`, `lead` or `other`, or any label mapped with `--roles LABEL=role`
(case-insensitive), e.g. the speaker names of a real export. An unmapped label is an error, never a
guess. Timestamps are synthetic (10 s per line); the Call carries the `synthetic_timestamps` flag.

Per input file: `<name>.json` + `<name>.md`; per run: `review_sheet.csv` (one row per file, human
columns empty) and a SUCCESS / INVALID / INPUT_TOO_LARGE / ERROR summary.

No silent truncation: every prompt goes through `ContextGuard`, which refuses (INPUT_TOO_LARGE) a
prompt that may not fit the model context, before sending it (conservative estimate) and after
(Ollama's reported prompt tokens). Nothing is chunked, summarized or cut; the call is not analyzed. Outputs contain transcript quotes: inside this
repository they may only go under the gitignored `artifacts/`; real calls belong outside it.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.ai.ollama_provider import DEFAULT_BASE_URL, OllamaClassificationProvider, OllamaError
from closer_ai.ai.post_call import PostCallIntelligence, analyze_call, render_markdown
from closer_ai.normalization.models import Call
from closer_ai.normalization.normalize import normalize_call

_REPO = Path(__file__).resolve().parents[3]
CLASSIFICATION_KB = _REPO / "docs" / "knowledge" / "sales" / "objections"
GUIDANCE_KB = _REPO / "docs" / "knowledge" / "sales" / "guidance"
_ROLES = ("closer", "lead", "other")
_SECONDS_PER_LINE = 10.0

REVIEW_COLUMNS = (
    "source_file", "call_id", "detected_category", "recommended_move", "knowledge_grade",
    "next_step_detected", "risk_count", "pipeline_status",
    "human_category_correct", "human_guidance_useful", "human_guidance_grounded",
    "human_next_step_correct", "human_better_recommendation", "human_error_category", "human_notes",
)
STATUSES = ("SUCCESS", "INVALID", "INPUT_TOO_LARGE", "ERROR")
DEFAULT_NUM_CTX = 16384
# Measured on qwen3:8b with these prompts: 3.1-3.6 chars/token. 2.5 overestimates tokens on purpose.
CHARS_PER_TOKEN_ESTIMATE = 2.5
OUTPUT_RESERVE_TOKENS = 2048


class InputTooLargeError(ValueError):
    """The prompt may not fit the model context; the call is not analyzed (never truncated)."""


class ContextGuard:
    """Provider wrapper: fail closed instead of letting Ollama silently truncate a long prompt.

    Before: conservative size estimate. After: Ollama's own `prompt_eval_count`, when reported
    (it can be lower than the real prompt when Ollama reuses a cached prefix, so it is only a second
    line of defence; the estimate is the primary check).
    """

    def __init__(self, inner: Any, num_ctx: int, reserve_tokens: int = OUTPUT_RESERVE_TOKENS,
                 chars_per_token: float = CHARS_PER_TOKEN_ESTIMATE) -> None:
        self.inner, self.num_ctx = inner, num_ctx
        self.budget = num_ctx - reserve_tokens
        self.chars_per_token = chars_per_token
        self.name, self.model = inner.name, inner.model

    def classify(self, prompt: str) -> Any:
        estimate = math.ceil(len(prompt) / self.chars_per_token)
        if estimate > self.budget:
            raise InputTooLargeError(
                f"prompt ~{estimate} tokens (estimate) exceeds the budget of {self.budget} "
                f"(num_ctx {self.num_ctx} - output reserve); call not analyzed, nothing truncated")
        result = self.inner.classify(prompt)
        used = getattr(self.inner, "last_usage", {}).get("prompt_eval_count")
        if isinstance(used, int) and used > self.budget:
            raise InputTooLargeError(f"model reported {used} prompt tokens > budget {self.budget}; "
                                     "output discarded (possible truncation)")
        return result


def parse_roles(spec: str | None) -> dict[str, str]:
    """'Renato=lead,Ana=closer' -> {'renato': 'lead', 'ana': 'closer'}."""
    roles: dict[str, str] = {}
    for item in filter(None, (part.strip() for part in (spec or "").split(","))):
        label, sep, role = item.partition("=")
        if not sep or not label.strip() or role.strip().lower() not in _ROLES:
            raise ValueError(f"--roles: expected LABEL=<{'|'.join(_ROLES)}>, got {item!r}")
        roles[label.strip().lower()] = role.strip().lower()
    return roles


def parse_transcript(text: str, source_id: str, roles: dict[str, str] | None = None) -> Call:
    roles = roles or {}
    segments, participants = [], {}
    for n, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, sep, utterance = line.partition(":")
        label = label.strip().lower()
        role = roles.get(label, label if label in _ROLES else None)
        if not sep or role is None or not utterance.strip():
            raise ValueError(f"line {n}: expected '<speaker>: <text>' with speaker in {_ROLES} or "
                             f"mapped by --roles; got label {label!r}")
        participants[label] = role
        i = len(segments)
        segments.append({"speaker_id": label, "start_ts": i * _SECONDS_PER_LINE,
                         "end_ts": (i + 1) * _SECONDS_PER_LINE, "text": utterance.strip()})
    if not segments:
        raise ValueError("transcript has no utterances")
    return normalize_call({
        "company_id": "demo",
        "source": "demo_txt",
        "source_id": source_id,
        "occurred_at": datetime(1970, 1, 1, tzinfo=UTC),  # unknown; not used by the pipeline
        "duration_seconds": len(segments) * _SECONDS_PER_LINE,
        "participants": [{"id": label, "role": role} for label, role in sorted(participants.items())],
        "segments": segments,
        "quality_flags": ["synthetic_timestamps"],
    })


def review_row(source_file: str, pci: PostCallIntelligence | None, failure: str = "ERROR") -> dict[str, str]:
    """One review-sheet row; human_* columns stay empty for Gabriel + closer to fill in."""
    row = dict.fromkeys(REVIEW_COLUMNS, "")
    row.update(source_file=source_file, pipeline_status=failure)
    if pci is not None:
        guided = [g for g in pci.commercial_guidance if g.status == "GUIDED"]
        row.update(
            call_id=pci.call_id,
            detected_category="; ".join(o.category or o.category_status for o in pci.objections) or "NONE",
            recommended_move="; ".join(g.knowledge_move_id for g in guided),
            knowledge_grade="; ".join(g.knowledge_grade for g in guided),
            next_step_detected="yes" if pci.next_steps else "no",
            risk_count=str(len(pci.risks)),
            pipeline_status=pci.pipeline_status,
        )
    return row


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m closer_ai.demo.analyze_call", description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path, help="transcript .txt files or directories of them")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--arm", default="E2", choices=("E0", "E1", "E2"))
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/demo"))
    ap.add_argument("--roles", help="map speaker labels to roles, e.g. 'Renato=lead,Ana=closer'")
    ap.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX,
                    help="model context window in tokens; prompts that may not fit are refused")
    ap.add_argument("--continue-on-error", action="store_true",
                    help="keep going after a call fails (default: stop at the first ERROR)")
    args = ap.parse_args(argv)

    out_dir = args.out_dir.resolve()
    if _inside(out_dir, _REPO) and not _inside(out_dir, _REPO / "artifacts"):
        ap.error(f"--out-dir {out_dir} is inside the repository; use artifacts/ or a folder outside it")
    roles = parse_roles(args.roles)
    files = [f for p in args.paths for f in (sorted(p.glob("*.txt")) if p.is_dir() else [p])]
    provider = ContextGuard(OllamaClassificationProvider(args.model, base_url=args.base_url, num_ctx=args.num_ctx),
                            num_ctx=args.num_ctx)
    guidance_kb = load_objection_knowledge(GUIDANCE_KB)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in files:
        try:
            call = parse_transcript(path.read_text(encoding="utf-8"), source_id=path.stem, roles=roles)
            pci = analyze_call(call, provider, CLASSIFICATION_KB, guidance_kb, arm=args.arm)
        except (ValueError, OSError, OllamaError) as exc:
            status = "INPUT_TOO_LARGE" if isinstance(exc, InputTooLargeError) else "ERROR"
            rows.append(review_row(path.name, None, failure=status))
            print(f"{status:<8} {path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                break
            continue
        (out_dir / f"{path.stem}.json").write_text(pci.to_json() + "\n", encoding="utf-8")
        (out_dir / f"{path.stem}.md").write_text(render_markdown(pci), encoding="utf-8")
        rows.append(review_row(path.name, pci))
        print(f"{pci.pipeline_status:<8} {path.name} -> {out_dir / path.stem}.{{json,md}}", file=sys.stderr)

    with (out_dir / "review_sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts = {s: sum(r["pipeline_status"] == s for r in rows) for s in STATUSES}
    skipped = len(files) - len(rows)
    print(f"summary: {' '.join(f'{k}={v}' for k, v in counts.items())}"
          f"{f' NOT_RUN={skipped}' if skipped else ''} -> {out_dir / 'review_sheet.csv'}", file=sys.stderr)
    return 1 if counts["ERROR"] or counts["INPUT_TOO_LARGE"] else 0


if __name__ == "__main__":
    sys.exit(main())
