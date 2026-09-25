"""Deal foundation policy (DI-M1 = 7a): a Canonical Deal is founded explicitly by one source
record; ingestion never founds a Deal per card. See DEAL_IDENTITY_RESOLUTION_PROPOSAL.md §7."""
from datetime import UTC, datetime

import pytest

from closer_ai.domain.deal import Deal, derive_deal_id
from closer_ai.domain.deal_identity import (
    DealIdentityConflict,
    DealIdentityDecision,
    append_deal_identity_decision,
    derive_deal_identity_decision_id,
    derive_source_record_key,
    found_deal,
    resolve_deal_for_source_record,
)

CO = "agrotalento-001"
T1 = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 7, 2, 10, 0, tzinfo=UTC)
T3 = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)


def deal(card="card-s", provider="kommo", **overrides):
    fields = {
        "current_stage": "negotiation", "outcome": "open", "created_at": T1, "closed_at": None,
    }
    fields.update(overrides)
    return Deal(
        deal_id=derive_deal_id(CO, provider, card), company_id=CO, source=provider,
        external_id=card, **fields,
    )


def key(card="card-s", provider="kommo"):
    return derive_source_record_key(CO, provider, card)


def dec(status, deal_id=None, *, card="card-s", candidates=(), by="manual", supersedes=None,
        at=T1):
    k = key(card)
    return DealIdentityDecision(
        identity_decision_id=derive_deal_identity_decision_id(
            k, status, deal_id, candidates, by, supersedes, at
        ),
        company_id=CO, provider="kommo", external_record_id=card, status=status,
        deal_id=deal_id, candidate_deal_ids=candidates, decided_by=by,
        supersedes_decision_id=supersedes, created_at=at,
    )


DEAL_X = derive_deal_id(CO, "kommo", "card-x")
DEAL_Y = derive_deal_id(CO, "kommo", "card-y")


# --- A, B, C, 1-3: foundation and idempotency -------------------------------------------------


def test_a_foundation_creates_linked_self_identity():
    d = deal()
    decision, history = found_deal(d, [], decided_by="automatic", decided_at=T1)
    assert decision.founds_deal and decision.deal_id == d.deal_id
    current = resolve_deal_for_source_record(key(), history)
    assert (current.state, current.deal_id) == ("linked", d.deal_id)


def test_1_foundation_deal_id_is_deterministic():
    assert deal().deal_id == deal().deal_id == derive_deal_id(CO, "kommo", "card-s")


def test_b_c_repeated_foundation_is_idempotent_never_a_second_deal():
    d = deal()
    first, history = found_deal(d, [], decided_by="automatic", decided_at=T1)
    again, history2 = found_deal(d, history, decided_by="manual", decided_at=T3)
    assert again == first and history2 == history


def test_foundation_ignores_legacy_projection_differences():
    # same record, different CRM projection values: same Deal, no new decision
    first, history = found_deal(deal(), [], decided_by="automatic", decided_at=T1)
    again, history2 = found_deal(
        deal(outcome="won", closed_at=T2, current_stage="proposal"), history,
        decided_by="automatic", decided_at=T2,
    )
    assert again == first and history2 == history


# --- 4, 5, J: identifiers ---------------------------------------------------------------------


def test_j_same_external_id_on_two_providers_founds_two_deals():
    kommo, _ = found_deal(deal("123", "kommo"), [], decided_by="automatic", decided_at=T1)
    pipe, _ = found_deal(deal("123", "pipedrive"), [], decided_by="automatic", decided_at=T1)
    assert kommo.deal_id != pipe.deal_id
    assert kommo.source_record_key != pipe.source_record_key


def test_5_different_records_found_different_deals():
    a, _ = found_deal(deal("card-1"), [], decided_by="automatic", decided_at=T1)
    b, _ = found_deal(deal("card-2"), [], decided_by="automatic", decided_at=T1)
    assert a.deal_id != b.deal_id


def test_6_foundation_uses_no_name_or_pii():
    fields = set(DealIdentityDecision.model_fields)
    assert not fields & {"name", "email", "phone", "lead_name", "company_name"}
    d = deal()
    decision, _ = found_deal(d, [], decided_by="automatic", decided_at=T1)
    assert decision.deal_id == derive_deal_id(d.company_id, d.source, d.external_id)


# --- D-H, 7-10: conflicts ---------------------------------------------------------------------


def test_d_record_manually_linked_to_another_deal_cannot_be_founded():
    manual = dec("linked", DEAL_X)
    with pytest.raises(DealIdentityConflict, match="another Deal"):
        found_deal(deal(), [manual], decided_by="manual", decided_at=T2)


def test_e_automatic_foundation_cannot_erase_ambiguity():
    amb = dec("ambiguous", candidates=(DEAL_X, DEAL_Y), by="automatic")
    with pytest.raises(DealIdentityConflict, match="ambiguity"):
        found_deal(deal(), [amb], decided_by="automatic", decided_at=T2)


def test_e_explicit_manual_foundation_may_resolve_ambiguity():
    amb = dec("ambiguous", candidates=(DEAL_X, DEAL_Y), by="automatic")
    decision, history = found_deal(deal(), [amb], decided_by="manual", decided_at=T2)
    assert decision.supersedes_decision_id == amb.identity_decision_id
    assert resolve_deal_for_source_record(key(), history).deal_id == deal().deal_id


def test_f_explicit_foundation_replaces_unresolved_linearly():
    unresolved = dec("unresolved", by="automatic")
    decision, history = found_deal(deal(), [unresolved], decided_by="automatic", decided_at=T2)
    assert decision.supersedes_decision_id == unresolved.identity_decision_id
    assert len(history) == 2


def test_f_automatic_foundation_cannot_replace_manual_unresolved():
    unresolved = dec("unresolved", by="manual")
    with pytest.raises(DealIdentityConflict, match="manual"):
        found_deal(deal(), [unresolved], decided_by="automatic", decided_at=T2)


def test_g_not_a_deal_blocks_automatic_foundation():
    nad = dec("not_a_deal")
    with pytest.raises(DealIdentityConflict, match="manual"):
        found_deal(deal(), [nad], decided_by="automatic", decided_at=T2)


def test_h_founder_cannot_be_relinked_or_unlinked():
    founding, history = found_deal(deal(), [], decided_by="automatic", decided_at=T1)
    for status, deal_id, candidates in (
        ("linked", DEAL_X, ()),
        ("unresolved", None, ()),
        ("not_a_deal", None, ()),
        ("ambiguous", None, (DEAL_X, DEAL_Y)),
    ):
        attempt = dec(status, deal_id, candidates=candidates,
                      supersedes=founding.identity_decision_id, at=T2)
        with pytest.raises(DealIdentityConflict, match="founder link is stable"):
            append_deal_identity_decision(history, attempt)


def test_founder_relink_written_outside_append_is_conflict():
    founding, _ = found_deal(deal(), [], decided_by="manual", decided_at=T1)
    relink = dec("linked", DEAL_X, supersedes=founding.identity_decision_id, at=T2)
    assert resolve_deal_for_source_record(key(), [founding, relink]).state == "conflict"
    with pytest.raises(DealIdentityConflict, match="not linear"):
        found_deal(deal(), [founding, relink], decided_by="manual", decided_at=T3)


def test_i_similar_record_has_no_effect_on_foundation():
    _, history_s = found_deal(deal("card-s"), [], decided_by="automatic", decided_at=T1)
    assert resolve_deal_for_source_record(key("card-s-copy"), []).state == "no_decision"
    assert all(d.source_record_key == key("card-s") for d in history_s)


def test_11_additional_record_is_not_linked_or_founded_automatically():
    found_deal(deal("card-s"), [], decided_by="automatic", decided_at=T1)
    other = resolve_deal_for_source_record(key("card-b"), [])
    assert (other.state, other.deal_id) == ("no_decision", None)
    # linking card-b to the founded Deal stays a normal manual identity decision
    link = dec("linked", deal("card-s").deal_id, card="card-b")
    assert resolve_deal_for_source_record(
        key("card-b"), append_deal_identity_decision([], link)
    ).deal_id == deal("card-s").deal_id


# --- 12-18: boundaries, chain, integrity ------------------------------------------------------


def test_12_13_foundation_creates_no_outcome_and_ignores_legacy_outcome():
    legacy = deal(outcome="won", closed_at=T2)
    decision, history = found_deal(legacy, [], decided_by="automatic", decided_at=T3)
    assert all(isinstance(d, DealIdentityDecision) for d in history)
    assert decision.status == "linked"  # nothing derived from legacy outcome "won"


def test_15_foundation_participates_in_linear_chain_and_cas():
    unresolved = dec("unresolved", by="automatic")
    founding, history = found_deal(deal(), [unresolved], decided_by="manual", decided_at=T2)
    stale = dec("unresolved", by="manual", supersedes=unresolved.identity_decision_id, at=T3)
    with pytest.raises(DealIdentityConflict, match="stale write"):
        append_deal_identity_decision(history, stale)
    assert resolve_deal_for_source_record(key(), history).decision_id == \
        founding.identity_decision_id


def test_16_same_id_different_payload_is_hard_error():
    founding, history = found_deal(deal(), [], decided_by="automatic", decided_at=T1)
    tampered = founding.model_copy(update={"deal_id": DEAL_X})
    with pytest.raises(ValueError, match="different payload"):
        append_deal_identity_decision(history, tampered)


def test_17_stale_concurrent_writer_does_not_win():
    unresolved = dec("unresolved", by="automatic")
    _, history = found_deal(deal(), [unresolved], decided_by="automatic", decided_at=T2)
    competing = dec("not_a_deal", supersedes=unresolved.identity_decision_id, at=T2)
    with pytest.raises(DealIdentityConflict, match="stale write"):
        append_deal_identity_decision(history, competing)


def test_foundation_rejects_history_of_another_record():
    with pytest.raises(ValueError, match="another source record"):
        found_deal(deal("card-s"), [dec("unresolved", card="card-b")], decided_by="manual",
                   decided_at=T1)


def test_g_manual_foundation_may_override_not_a_deal():
    nad = dec("not_a_deal")
    decision, history = found_deal(deal(), [nad], decided_by="manual", decided_at=T2)
    assert resolve_deal_for_source_record(key(), history).deal_id == decision.deal_id


def test_idempotent_when_manual_founds_first_then_automatic():
    first, history = found_deal(deal(), [], decided_by="manual", decided_at=T1)
    again, history2 = found_deal(deal(), history, decided_by="automatic", decided_at=T2)
    assert again == first and history2 == history


def test_two_founding_roots_written_outside_append_are_conflict():
    a, _ = found_deal(deal(), [], decided_by="automatic", decided_at=T1)
    b, _ = found_deal(deal(), [], decided_by="manual", decided_at=T2)
    assert resolve_deal_for_source_record(key(), [a, b]).state == "conflict"


def test_automatic_attempt_to_unlink_founder_is_refused():
    founding, history = found_deal(deal(), [], decided_by="automatic", decided_at=T1)
    attempt = dec("unresolved", by="automatic", supersedes=founding.identity_decision_id, at=T2)
    with pytest.raises(DealIdentityConflict, match="founder link is stable"):
        append_deal_identity_decision(history, attempt)
