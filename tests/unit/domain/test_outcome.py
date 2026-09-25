"""Outcome Domain v0 — structural core. Contract: docs/domain/OUTCOME_CONTRACT_V0_PROPOSAL.md,
docs/decisions/ADR_001-outcome-contract-v0.md. No commercial policy is exercised here: every
assessment is hand-built, the way a future policy or a human would build it."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from closer_ai.domain.deal import Deal, derive_deal_id
from closer_ai.domain.outcome import (
    EvidenceDisposition,
    OutcomeAssessment,
    OutcomeConflict,
    OutcomeEvidence,
    append_evidence_disposition,
    append_outcome_assessment,
    append_outcome_evidence,
    derive_evidence_disposition_id,
    derive_outcome_assessment_id,
    derive_outcome_evidence_id,
    resolve_current_outcome,
    resolve_eligible_evidence,
)

DEAL = derive_deal_id("agrotalento-001", "kommo", "card-1")
OTHER_DEAL = derive_deal_id("agrotalento-001", "kommo", "card-2")
T1 = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
T3 = datetime(2026, 4, 3, 10, 0, tzinfo=UTC)
T4 = datetime(2026, 4, 4, 10, 0, tzinfo=UTC)


def ev(signal="unclassified", *, source="crm_status", key="status", raw="ABERTO", ref="card-1",
       at=T1, deal=DEAL):
    raw = raw if source != "crm_note" else None
    return OutcomeEvidence(
        evidence_id=derive_outcome_evidence_id(deal, source, ref, key, raw, signal, at),
        deal_id=deal, source=source, source_record_ref=ref, observation_key=key,
        raw_state=raw, signal=signal, observed_at=at,
    )


def disp(target, kind="invalidated", *, replacement=None, by="human", mapping=None, at=T2):
    rid = replacement.evidence_id if replacement is not None else None
    return EvidenceDisposition(
        disposition_id=derive_evidence_disposition_id(
            target.evidence_id, kind, rid, by, mapping, at
        ),
        evidence_id=target.evidence_id, kind=kind, replacement_evidence_id=rid,
        decided_by=by, mapping_version=mapping, decided_at=at,
    )


def asm(status, supporting=(), eligible=None, *, method="rule", review=False, conf="default",
        effective=None, decided=T3, supersedes=None, deal=DEAL):
    supporting = tuple(e.evidence_id for e in supporting)
    eligible = supporting if eligible is None else tuple(e.evidence_id for e in eligible)
    if conf == "default":
        conf = None if status == "unknown" else ("high" if method == "human" else "medium")
    if effective is None and status in ("won", "rejected"):
        effective = T1
    policy = "policy-test-1" if method == "rule" else None
    return OutcomeAssessment(
        assessment_id=derive_outcome_assessment_id(
            deal, status, supporting, eligible, conf, review, method, policy, effective, decided,
            supersedes,
        ),
        deal_id=deal, status=status, supporting_evidence_ids=supporting,
        eligible_evidence_ids=eligible, confidence_level=conf, needs_human_review=review,
        decision_method=method, policy_version=policy, effective_at=effective, decided_at=decided,
        supersedes_assessment_id=supersedes,
    )


def chain(*assessments, evidence=(), dispositions=()):
    history = []
    for a in assessments:
        history = append_outcome_assessment(
            history, a, evidence=list(evidence), dispositions=list(dispositions)
        )
    return history


# --- 1-4: evidence identity and idempotency ---------------------------------------------------


def test_1_evidence_id_is_deterministic():
    assert ev().evidence_id == ev().evidence_id
    assert ev().evidence_id.startswith("oev_")


def test_2_two_observations_of_the_same_record_do_not_collide():
    stage = ev(key="stage", raw="NEGOCIAÇÃO")
    status = ev(key="status", raw="ABERTO")
    assert stage.evidence_id != status.evidence_id


def test_evidence_id_contains_no_raw_text():
    e = ev(raw="Fechado - perdido por João")
    assert "João" not in e.evidence_id and "perdido" not in e.evidence_id


def test_3_identical_redelivery_is_idempotent():
    store = append_outcome_evidence([], ev())
    assert append_outcome_evidence(store, ev()) == store


def test_4_same_id_different_payload_is_hard_error():
    original = ev()
    tampered = original.model_copy(update={"raw_state": "PERDIDO"})
    with pytest.raises(ValueError, match="different payload"):
        append_outcome_evidence([original], tampered)
    with pytest.raises(ValueError, match="different payload"):
        resolve_eligible_evidence(DEAL, [original, tampered], [])


def test_forged_evidence_id_is_rejected():
    with pytest.raises(ValidationError, match="evidence_id"):
        OutcomeEvidence(
            evidence_id="oev_forged", deal_id=DEAL, source="crm_status", source_record_ref="c",
            observation_key="status", raw_state="ABERTO", signal="unclassified", observed_at=T1,
        )


def test_crm_status_requires_raw_state_and_notes_never_store_text():
    with pytest.raises(ValidationError, match="raw_state is required"):
        OutcomeEvidence(
            evidence_id=derive_outcome_evidence_id(DEAL, "crm_status", "c", "k", None, "sale", T1),
            deal_id=DEAL, source="crm_status", source_record_ref="c", observation_key="k",
            raw_state=None, signal="sale", observed_at=T1,
        )
    with pytest.raises(ValidationError, match="free-text"):
        OutcomeEvidence(
            evidence_id=derive_outcome_evidence_id(DEAL, "crm_note", "c", "k", "txt", "sale", T1),
            deal_id=DEAL, source="crm_note", source_record_ref="c", observation_key="k",
            raw_state="txt", signal="sale", observed_at=T1,
        )


# --- 5-7: eligibility -------------------------------------------------------------------------


def test_no_disposition_everything_is_eligible():
    a, b = ev("sale", source="payment", key="p1"), ev()
    assert {e.evidence_id for e in resolve_eligible_evidence(DEAL, [a, b], [])} == {
        a.evidence_id, b.evidence_id,
    }


def test_5_invalidated_evidence_is_not_eligible_but_still_exists():
    payment = ev("sale", source="payment", key="p1")
    d = disp(payment)
    assert resolve_eligible_evidence(DEAL, [payment], [d]) == ()


def test_6_remapped_evidence_old_interpretation_is_not_eligible():
    old = ev("rejection", key="status", raw="PERDIDO")
    new = ev("no_contact", key="status", raw="PERDIDO")
    d = disp(old, "remapped", replacement=new, by="mapping", mapping="dep3-v2")
    eligible = resolve_eligible_evidence(DEAL, [old, new], [d])
    assert [e.evidence_id for e in eligible] == [new.evidence_id]


def test_remap_replacement_must_be_same_observation_with_different_signal():
    old = ev("rejection", key="status", raw="PERDIDO")
    other_observation = ev("no_contact", key="stage", raw="PERDIDO")
    with pytest.raises(ValueError, match="same observation"):
        append_evidence_disposition(
            [], disp(old, "remapped", replacement=other_observation), [old, other_observation]
        )


def test_7_disposition_for_evidence_of_another_deal_is_rejected():
    foreign = ev("sale", source="payment", key="p9", deal=OTHER_DEAL)
    mine = ev()
    with pytest.raises(ValueError, match="unknown evidence"):
        resolve_eligible_evidence(DEAL, [mine], [disp(foreign)])
    with pytest.raises(ValueError, match="another deal"):
        resolve_eligible_evidence(DEAL, [mine, foreign], [])


def test_disposition_targeting_missing_evidence_is_rejected():
    ghost = ev("sale", source="payment", key="ghost")
    with pytest.raises(ValueError, match="unknown evidence"):
        append_evidence_disposition([], disp(ghost), [ev()])


def test_second_disposition_on_same_evidence_is_hard_error_identical_is_idempotent():
    e = ev("sale", source="payment", key="p1")
    first = disp(e, at=T2)
    store = append_evidence_disposition([], first, [e])
    assert append_evidence_disposition(store, first, [e]) == store
    with pytest.raises(ValueError, match="already has a disposition"):
        append_evidence_disposition(store, disp(e, at=T3), [e])


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"kind": "invalidated", "by": "mapping", "mapping": "v2"}, "only a human"),
        ({"kind": "invalidated", "by": "human", "mapping": "v2"}, "mapping_version"),
    ],
)
def test_disposition_model_invariants(kwargs, message):
    with pytest.raises(ValidationError, match=message):
        disp(ev(), **kwargs)


# --- 8-9: assessment references ---------------------------------------------------------------


def test_8_assessment_cannot_reference_evidence_of_another_deal():
    foreign = ev("sale", source="payment", key="p1", deal=OTHER_DEAL)
    a = asm("won", [foreign])
    with pytest.raises(OutcomeConflict, match="eligible"):
        append_outcome_assessment([], a, evidence=[], dispositions=[])


def test_9_supporting_must_be_subset_of_eligible():
    sale = ev("sale", source="payment", key="p1")
    with pytest.raises(ValidationError, match="subset"):
        asm("won", [sale], eligible=[])


def test_supporting_differs_from_eligible():
    sale = ev("sale", source="payment", key="p1")
    noise = ev()
    history = chain(asm("won", [sale], eligible=[sale, noise]), evidence=[sale, noise])
    canonical = resolve_current_outcome(DEAL, history).canonical
    assert canonical.supporting_evidence_ids == (sale.evidence_id,)
    assert set(canonical.eligible_evidence_ids) == {sale.evidence_id, noise.evidence_id}


def test_assessment_citing_invalidated_evidence_is_refused():
    sale = ev("sale", source="payment", key="p1")
    d = disp(sale)
    with pytest.raises(OutcomeConflict, match="eligible"):
        append_outcome_assessment([], asm("won", [sale]), evidence=[sale], dispositions=[d])


# --- decision bundle (P0-3) invariants --------------------------------------------------------


def test_unknown_cannot_carry_confidence():
    with pytest.raises(ValidationError, match="confidence_level"):
        asm("unknown", conf="high")


def test_won_without_supporting_evidence_is_invalid():
    with pytest.raises(ValidationError, match="at least one supporting"):
        asm("won", [])


def test_won_requires_sale_signal_in_support():
    active = ev("active", source="closer_report", key="r1", raw=None)
    with pytest.raises(ValueError, match="sale"):
        chain(asm("won", [active]), evidence=[active])


@pytest.mark.parametrize(
    "evidence_kwargs",
    [
        {"signal": "no_contact", "source": "automation", "key": "bot"},
        {"signal": "reversal", "source": "payment", "key": "refund"},
        {"signal": "rejection", "source": "automation", "key": "bot2"},
    ],
)
def test_rejected_never_supported_by_no_contact_reversal_or_automation(evidence_kwargs):
    real = ev("rejection", source="closer_report", key="r1", raw=None)
    bad = ev(raw=None, **evidence_kwargs)
    with pytest.raises(ValueError, match="never support"):
        chain(asm("rejected", [real, bad]), evidence=[real, bad])


def test_effective_at_required_iff_terminal_and_not_after_decision():
    sale = ev("sale", source="payment", key="p1")
    with pytest.raises(ValidationError, match="effective_at"):
        asm("open", [ev("active", source="closer_report", key="r", raw=None)], effective=T1)
    with pytest.raises(ValidationError, match="after decided_at"):
        asm("won", [sale], effective=T4, decided=T3)


def test_human_decision_never_needs_review_and_has_no_policy():
    with pytest.raises(ValidationError, match="never needs human review"):
        asm("unknown", method="human", review=True)
    with pytest.raises(ValidationError, match="policy_version"):
        OutcomeAssessment(
            assessment_id="x", deal_id=DEAL, status="unknown", supporting_evidence_ids=(),
            eligible_evidence_ids=(), confidence_level=None, needs_human_review=False,
            decision_method="rule", policy_version=None, decided_at=T3,
        )


def test_forged_assessment_id_is_rejected():
    with pytest.raises(ValidationError, match="assessment_id"):
        OutcomeAssessment(
            assessment_id="oas_forged", deal_id=DEAL, status="unknown",
            supporting_evidence_ids=(), eligible_evidence_ids=(), confidence_level=None,
            needs_human_review=False, decision_method="human", decided_at=T3,
        )


# --- 10-15: linear history and CAS ------------------------------------------------------------


def test_10_linear_history_resolves_to_head():
    a = asm("unknown", decided=T2)
    b = asm("unknown", decided=T3, supersedes=a.assessment_id, review=True)
    assert resolve_current_outcome(DEAL, chain(a, b)).canonical == b


def test_11_multiple_heads_is_conflict_never_a_winner():
    a = asm("unknown", decided=T1)
    b = asm("unknown", decided=T2, supersedes=a.assessment_id, review=True)
    c = asm("unknown", decided=T3, supersedes=a.assessment_id, conf=None)
    result = resolve_current_outcome(DEAL, [a, b, c])
    assert (result.state, result.canonical, result.status) == ("conflict", None, None)


def test_12_cycle_or_rootless_history_is_conflict():
    x = asm("unknown", decided=T1, supersedes="oas_ghost_y")
    y = asm("unknown", decided=T2, supersedes=x.assessment_id)
    assert resolve_current_outcome(DEAL, [x, y]).state == "conflict"


def test_13_dangling_supersession_is_conflict():
    a = asm("unknown", decided=T1)
    b = asm("unknown", decided=T2, supersedes="oas_missing", review=True)
    assert resolve_current_outcome(DEAL, [a, b]).state == "conflict"


def test_14_cross_deal_supersession_is_invalid():
    theirs = asm("unknown", deal=OTHER_DEAL)
    mine = asm("unknown", supersedes=theirs.assessment_id, review=True)
    with pytest.raises(ValueError, match="another deal"):
        resolve_current_outcome(DEAL, [theirs])
    with pytest.raises(OutcomeConflict, match="stale write"):
        append_outcome_assessment([], mine, evidence=[], dispositions=[])


def test_15_stale_writer_fails_first_writer_wins():
    a = asm("unknown", decided=T1)
    first = asm("unknown", decided=T2, supersedes=a.assessment_id, review=True)
    second = asm("unknown", decided=T3, supersedes=a.assessment_id, review=True)
    history = chain(a, first)
    with pytest.raises(OutcomeConflict, match="stale write"):
        append_outcome_assessment(history, second, evidence=[], dispositions=[])


def test_stale_eligible_set_fails_cas():
    sale = ev("sale", source="payment", key="p1")
    newer = ev("reversal", source="payment", key="refund", at=T2)
    stale = asm("won", [sale])  # built before the refund evidence arrived
    with pytest.raises(OutcomeConflict, match="eligible"):
        append_outcome_assessment([], stale, evidence=[sale, newer], dispositions=[])


def test_cannot_append_to_forked_history():
    a = asm("unknown", decided=T1)
    b = asm("unknown", decided=T2, supersedes=a.assessment_id, review=True)
    c = asm("unknown", decided=T3, supersedes=a.assessment_id, conf=None)
    with pytest.raises(OutcomeConflict, match="linear"):
        append_outcome_assessment(
            [a, b, c], asm("unknown", decided=T4, supersedes=b.assessment_id),
            evidence=[], dispositions=[],
        )


def test_assessment_redelivery_idempotent_and_tamper_is_error():
    a = asm("unknown")
    history = chain(a)
    assert append_outcome_assessment(history, a, evidence=[], dispositions=[]) == history
    with pytest.raises(ValueError, match="different payload"):
        append_outcome_assessment(
            history, a.model_copy(update={"needs_human_review": True}),
            evidence=[], dispositions=[],
        )


def test_decided_at_never_orders_the_chain():
    a = asm("unknown", decided=T4)
    b = asm("unknown", decided=T1, supersedes=a.assessment_id, review=True)
    assert resolve_current_outcome(DEAL, list(reversed(chain(a, b)))).canonical == b


# --- 16-18: human authority -------------------------------------------------------------------


def test_16_human_rejected_persists_through_rule_candidate():
    rej = ev("rejection", source="closer_report", key="r1", raw=None, at=T1)
    act = ev("active", source="closer_report", key="r2", raw=None, at=T2)
    h1 = asm("rejected", [rej], eligible=[rej], method="human", decided=T2)
    r1 = asm("open", [act], eligible=[act, rej], review=True, decided=T3,
             supersedes=h1.assessment_id)
    history = chain(h1, evidence=[rej])
    history = append_outcome_assessment(history, r1, evidence=[rej, act], dispositions=[])
    result = resolve_current_outcome(DEAL, history)
    assert result.canonical == h1
    assert (result.state, result.status, result.is_consumable) == ("review_pending", "rejected", False)


def test_human_unknown_persists_over_rule_won_candidate():
    sale = ev("sale", source="payment", key="p1", at=T2)
    h1 = asm("unknown", method="human", decided=T1)
    r1 = asm("won", [sale], review=True, decided=T3, supersedes=h1.assessment_id,
             effective=T2)
    history = append_outcome_assessment(chain(h1), r1, evidence=[sale], dispositions=[])
    result = resolve_current_outcome(DEAL, history)
    assert result.canonical == h1 and result.status == "unknown"
    assert result.state == "review_pending"


def test_17_authority_survives_several_rule_records_not_just_the_head():
    h1 = asm("unknown", method="human", decided=T1)
    r1 = asm("unknown", decided=T2, supersedes=h1.assessment_id, review=True)
    r2 = asm("unknown", decided=T3, supersedes=r1.assessment_id)
    result = resolve_current_outcome(DEAL, chain(h1, r1, r2))
    assert result.canonical == h1
    assert result.state == "available"  # head r2 no longer asks for review


def test_18_new_human_decision_replaces_previous_human():
    sale = ev("sale", source="payment", key="p1")
    h1 = asm("unknown", eligible=[sale], method="human", decided=T2)
    h2 = asm("won", [sale], method="human", decided=T3, supersedes=h1.assessment_id)
    history = chain(h1, h2, evidence=[sale])
    result = resolve_current_outcome(DEAL, history)
    assert result.canonical == h2 and result.is_consumable


def test_human_won_then_refund_candidate_keeps_whole_human_bundle():
    sale = ev("sale", source="payment", key="p1", at=T1)
    refund = ev("reversal", source="payment", key="refund", at=T2)
    h1 = asm("won", [sale], method="human", decided=T1)
    r1 = asm("unknown", [sale, refund], eligible=[sale, refund], review=True, decided=T3,
             supersedes=h1.assessment_id)
    history = append_outcome_assessment(chain(h1, evidence=[sale]), r1,
                                        evidence=[sale, refund], dispositions=[])
    result = resolve_current_outcome(DEAL, history)
    assert result.canonical == h1  # status, confidence, support and effective_at all from h1
    assert result.canonical.confidence_level == "high" and not result.is_consumable


def test_rule_leaving_terminal_without_new_evidence_is_refused():
    sale = ev("sale", source="payment", key="p1", at=T1)
    r1 = asm("won", [sale], decided=T2)
    r2 = asm("unknown", eligible=[sale], decided=T3, supersedes=r1.assessment_id)
    with pytest.raises(ValueError, match="leaving 'won'"):
        chain(r1, r2, evidence=[sale])


def test_rule_leaving_terminal_with_unchanged_multi_evidence_support_is_refused():
    # effective_at is the earliest support; a later piece of the SAME support is not "new"
    sale1 = ev("sale", source="payment", key="p1", at=T1)
    sale2 = ev("sale", source="payment", key="p2", at=T2)
    r1 = asm("won", [sale1, sale2], effective=T1, decided=T3)
    r2 = asm("unknown", eligible=[sale1, sale2], decided=T4, supersedes=r1.assessment_id)
    with pytest.raises(ValueError, match="leaving 'won'"):
        chain(r1, r2, evidence=[sale1, sale2])


def test_rule_leaving_terminal_with_genuinely_new_evidence_is_allowed():
    sale = ev("sale", source="payment", key="p1", at=T1)
    refund = ev("reversal", source="payment", key="refund", at=T2)
    r1 = asm("won", [sale], decided=T2)
    history = chain(r1, evidence=[sale])
    r2 = asm("unknown", [sale, refund], eligible=[sale, refund], review=True, decided=T3,
             supersedes=r1.assessment_id)
    history = append_outcome_assessment(history, r2, evidence=[sale, refund], dispositions=[])
    assert resolve_current_outcome(DEAL, history).state == "review_pending"


def test_rule_leaving_terminal_after_support_invalidated_is_allowed():
    sale = ev("sale", source="payment", key="p1", at=T1)
    r1 = asm("won", [sale], decided=T2)
    history = chain(r1, evidence=[sale])
    d = disp(sale, at=T3)
    r2 = asm("unknown", eligible=[], decided=T4, supersedes=r1.assessment_id)
    history = append_outcome_assessment(history, r2, evidence=[sale], dispositions=[d])
    assert resolve_current_outcome(DEAL, history).status == "unknown"


# --- 19-24: resolver states -------------------------------------------------------------------


def test_19_no_assessment_is_not_conflict():
    result = resolve_current_outcome(DEAL, [])
    assert (result.state, result.canonical, result.is_consumable) == ("no_assessment", None, False)


def test_20_21_review_pending_is_not_no_assessment_and_not_consumable():
    result = resolve_current_outcome(DEAL, chain(asm("unknown", review=True)))
    assert result.state == "review_pending"
    assert result.canonical is not None and not result.is_consumable


def test_22_unknown_is_a_legitimate_consumable_outcome():
    result = resolve_current_outcome(DEAL, chain(asm("unknown")))
    assert (result.state, result.status, result.is_consumable) == ("available", "unknown", True)


def test_23_no_evidence_cannot_produce_won_or_rejected():
    for status in ("won", "rejected", "open"):
        with pytest.raises(ValidationError, match="at least one supporting"):
            asm(status, [])


def test_24_legacy_deal_outcome_is_never_the_canonical_outcome():
    legacy = Deal(
        deal_id=DEAL, company_id="agrotalento-001", source="kommo", external_id="card-1",
        current_stage="negotiation", outcome="won", created_at=T1, closed_at=T2,
    )
    assert legacy.outcome == "won"
    result = resolve_current_outcome(legacy.deal_id, [])
    assert (result.state, result.status) == ("no_assessment", None)
