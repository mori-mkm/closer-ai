"""Long-call orchestration (pilot): run the existing pipeline on a call that does not fit the context.

    fits the context budget?  yes -> post_call.analyze_call (single_context, unchanged)
                              no  -> plan chunks -> E2 classifier per chunk -> merge episodes
                                     -> existing guide_episode per merged episode
                                     -> existing post-call extraction per chunk -> merge -> risks

Orchestration only: classifier, provider, guidance, grounding and the output contracts are reused
as they are. Design decisions worth knowing:

- Chunks are runs of whole utterances (never split), in call order, sized by the same estimate the
  ContextGuard enforces (`max_prompt_chars`), measured on the arm's real prompt (instructions + E2
  knowledge + transcript); the guard's output reserve is already inside that budget.
- Chunks are planned backwards from the end, so the final chunk is full: the lead's end position is
  read from it (the last chunk with a lead utterance), never averaged across chunks.
- Neighbouring chunks overlap by `OVERLAP` utterances, so an objection on a boundary is seen with
  context. Overlap duplicates (same category, shared objection segment) are merged deterministically,
  keeping the prediction with more context (tie: earlier chunk). No LLM is used to merge.
- A chunk Call keeps call_id, segment_id, speaker, role, text and order; only segment_index is
  renumbered (a Call requires 0..n-1). Quotes are always taken from the full Call.
- Fail closed: a provider/parse exception in any chunk propagates (the call gets no output); a chunk
  whose classifier run is invalid contributes no episodes and its errors make the call INVALID.
- No summarization, no truncation, no second pass over the whole transcript.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from closer_ai.ai.grounding import normalize
from closer_ai.ai.objection_classifier import (
    Arm,
    ClassificationProvider,
    EpisodePrediction,
    build_prompt,
    classify_call,
    render_call_facts,
)
from closer_ai.ai.objection_guidance import (
    ENGINE_VERSION,
    ObjectionKnowledge,
    guide_episode,
    quotes,
)
from closer_ai.ai.post_call import (
    LeadEndPosition,
    NextStep,
    ObjectionFinding,
    PostCallIntelligence,
    Stakeholder,
    analyze_call,
    build_post_call_prompt,
    derive_risks,
    extract_post_call,
)
from closer_ai.normalization.models import Call

OVERLAP = 2  # utterances shared by neighbouring chunks


class ChunkTooLargeError(ValueError):
    """A single utterance does not fit the context budget; it is never split."""


def _sub_call(call: Call, start: int, end: int) -> Call:
    segments = sorted(call.segments, key=lambda s: s.segment_index)[start:end]
    return call.model_copy(update={
        "segments": [s.model_copy(update={"segment_index": i}) for i, s in enumerate(segments)],
    })


def _greedy(sizes: list[int], fixed: int, cap: int, overlap: int, ids: list[str], max_prompt_chars: int
            ) -> list[tuple[int, int]]:
    """Fill chunks backwards from the end, each prompt <= cap chars."""
    chunks: list[tuple[int, int]] = []
    end = len(sizes)
    while True:
        start, used = end, fixed
        while start > 0 and used + sizes[start - 1] <= cap:
            start -= 1
            used += sizes[start]
        if start == end:
            raise ChunkTooLargeError(
                f"instructions + knowledge ({fixed} chars) + utterance {ids[end - 1]} "
                f"({sizes[end - 1]} chars) exceed the context budget ({max_prompt_chars} chars); "
                "an utterance is never split")
        chunks.append((start, end))
        if start == 0:
            return chunks[::-1]
        end = start + (overlap if end - start > overlap else 0)


def plan_chunks(call: Call, arm: Arm, knowledge_root: Path, max_prompt_chars: int,
                overlap: int = OVERLAP) -> list[tuple[int, int]]:
    """[start, end) segment ranges covering the call in order, each fitting `max_prompt_chars`.

    The chunk count is the minimum the budget allows; the chunks are then balanced by using the
    smallest per-chunk cap that still yields that count (binary search), so there is no tiny chunk.
    """
    segments = sorted(call.segments, key=lambda s: s.segment_index)
    roles = {p.id: p.role for p in call.participants}
    ids = [s.segment_id for s in segments]
    # Exact prompt length = fixed part + one rendered block per segment (render_call_facts joins
    # "\n[<id> | <role>]\n<text>" blocks with "\n").
    sizes = [len(f"\n[{s.segment_id} | {roles[s.speaker_id]}]\n{s.text}") + 1 for s in segments]
    fixed = len(build_prompt(call, arm, knowledge_root)) - len(render_call_facts(call)) + len("FACTS FROM CALL")
    best = _greedy(sizes, fixed, max_prompt_chars, overlap, ids, max_prompt_chars)
    lo, hi = fixed + max(sizes), max_prompt_chars
    while lo < hi:
        cap = (lo + hi) // 2
        try:
            fits = len(_greedy(sizes, fixed, cap, overlap, ids, max_prompt_chars)) <= len(best)
        except ChunkTooLargeError:
            fits = False
        if fits:
            hi = cap
        else:
            lo = cap + 1
    return _greedy(sizes, fixed, lo, overlap, ids, max_prompt_chars)


def _key(e: EpisodePrediction) -> tuple:
    return (e.category_status, e.category, tuple(sorted(e.category_candidates)))


def merge_episodes(per_chunk: list[tuple[int, tuple[EpisodePrediction, ...]]]
                   ) -> tuple[list[EpisodePrediction], dict[str, list[int]]]:
    """Deduplicate overlap duplicates: same category key and a shared objection segment."""
    kept: list[EpisodePrediction] = []
    chunks_of: dict[str, list[int]] = {}
    for index, episodes in per_chunk:
        for e in episodes:
            e = dataclasses.replace(e, prediction_id=f"c{index}.{e.prediction_id}")
            twin = next((k for k in kept if _key(k) == _key(e)
                         and set(k.objection_segment_ids) & set(e.objection_segment_ids)), None)
            if twin is None:
                kept.append(e)
                chunks_of[e.prediction_id] = [index]
            elif len(e.context_segment_ids) > len(twin.context_segment_ids):
                kept[kept.index(twin)] = e  # same episode seen with more context in a later chunk
                chunks_of[e.prediction_id] = [*chunks_of.pop(twin.prediction_id), index]
            else:
                chunks_of[twin.prediction_id].append(index)
    return kept, chunks_of


def _merge_stakeholders(items: list[Stakeholder]) -> tuple[Stakeholder, ...]:
    merged: dict[str, Stakeholder] = {}
    for s in items:
        key = normalize(s.who)
        if key in merged:
            seen = {q.segment_id for q in merged[key].evidence}
            merged[key] = dataclasses.replace(
                merged[key], evidence=(*merged[key].evidence, *(q for q in s.evidence if q.segment_id not in seen)))
        else:
            merged[key] = s
    return tuple(merged.values())


def _merge_steps(items: list[NextStep]) -> tuple[NextStep, ...]:
    """Same owner and due date citing a shared segment = the same commitment; keep the first."""
    kept: list[NextStep] = []
    for s in items:
        ids = {q.segment_id for q in s.evidence}
        if not any(k.owner == s.owner and normalize(k.due_date or "") == normalize(s.due_date or "")
                   and ids & {q.segment_id for q in k.evidence} for k in kept):
            kept.append(s)
    return tuple(kept)


def analyze_long_call(call: Call, provider: ClassificationProvider, knowledge_root: Path,
                      guidance_knowledge: ObjectionKnowledge, max_prompt_chars: int,
                      arm: Arm = "E2") -> PostCallIntelligence:
    plan = plan_chunks(call, arm, knowledge_root, max_prompt_chars)
    chunk_calls = [_sub_call(call, start, end) for start, end in plan]
    errors: list[str] = []
    per_chunk, chunk_meta = [], []
    for index, (chunk, (start, end)) in enumerate(zip(chunk_calls, plan, strict=True)):
        run = classify_call(chunk, arm, provider, knowledge_root=knowledge_root)
        errors += [f"chunk {index} classifier: {e}" for e in run.validation_errors]
        per_chunk.append((index, () if run.validation_errors else run.episodes))
        chunk_meta.append({"chunk_index": index, "first_segment_index": start, "last_segment_index": end - 1,
                           "segment_count": end - start, "classifier_prompt_sha256": run.prompt_sha256,
                           "call_detection": run.call_detection, "classifier_valid": run.valid})

    episodes, chunks_of = merge_episodes(per_chunk)
    position_of = {s.segment_id: s.segment_index for s in call.segments}
    episodes.sort(key=lambda e: position_of[e.anchor_segment_id])
    objections = tuple(
        ObjectionFinding(e.prediction_id, e.category_status, e.category, e.category_candidates,
                         quotes(call, e.objection_segment_ids), e.resolution_status, e.summary)
        for e in episodes)
    guidance = tuple(guide_episode(call, e, guidance_knowledge, provider) for e in episodes)
    errors += [f"guidance {g.prediction_id}: {e}" for g in guidance if g.status == "INVALID_RESPONSE"
               for e in g.errors]

    stakeholders, steps = [], []
    position = LeadEndPosition("UNKNOWN", ())
    lead_ids = {p.id for p in call.participants if p.role == "lead"}
    last_substantive = max((i for i, c in enumerate(chunk_calls)
                            if any(s.speaker_id in lead_ids for s in c.segments)), default=len(chunk_calls) - 1)
    for index, chunk in enumerate(chunk_calls):
        pos, chunk_stakeholders, chunk_steps, chunk_errors = extract_post_call(
            chunk, provider.classify(build_post_call_prompt(chunk)))
        errors += [f"chunk {index} post-call: {e}" for e in chunk_errors]
        stakeholders += chunk_stakeholders
        steps += chunk_steps
        if index == last_substantive:
            position = pos
    stakeholders_t, steps_t = _merge_stakeholders(stakeholders), _merge_steps(steps)

    detections = {m["call_detection"] for m in chunk_meta}
    return PostCallIntelligence(
        call_id=call.call_id,
        objections=objections,
        commercial_guidance=guidance,
        lead_end_position=position,
        stakeholders=stakeholders_t,
        next_steps=steps_t,
        risks=derive_risks(objections, position, stakeholders_t, steps_t),
        provenance={
            "engine_version": ENGINE_VERSION,
            "provider": provider.name,
            "model": provider.model,
            "classifier_arm": arm,
            "classifier_call_detection": "OBJECTIONS_FOUND" if episodes else
                                         ("NO_OBJECTION" if detections == {"NO_OBJECTION"} else "UNKNOWN"),
            "classification_knowledge_sha256": None,
            "guidance_knowledge_sha256": guidance_knowledge.sha256,
            "processing_mode": "chunked",
            "chunk_count": len(plan),
            "segment_count": len(call.segments),
            "segments_processed": len({i for start, end in plan for i in range(start, end)}),
            "chunk_overlap": OVERLAP,
            "lead_end_position_chunk": last_substantive,
            "chunks": chunk_meta,
            "episode_chunks": chunks_of,
        },
        errors=tuple(errors),
    )


def analyze_call_auto(call: Call, provider: ClassificationProvider, knowledge_root: Path,
                      guidance_knowledge: ObjectionKnowledge, max_prompt_chars: int,
                      arm: Arm = "E2") -> PostCallIntelligence:
    """single_context when the arm's prompt fits the budget, else chunked. The user never chooses."""
    if len(build_prompt(call, arm, knowledge_root)) <= max_prompt_chars:
        pci = analyze_call(call, provider, knowledge_root, guidance_knowledge, arm=arm)
        return dataclasses.replace(pci, provenance={
            **pci.provenance, "processing_mode": "single_context", "chunk_count": 1,
            "segment_count": len(call.segments), "segments_processed": len(call.segments)})
    return analyze_long_call(call, provider, knowledge_root, guidance_knowledge, max_prompt_chars, arm=arm)
