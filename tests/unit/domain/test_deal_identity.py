"""DEP-2: source record (CRM card) -> canonical Deal identity. See
docs/domain/DEAL_IDENTITY_RESOLUTION_PROPOSAL.md."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from closer_ai.domain.deal import derive_deal_id
from closer_ai.domain.deal_identity import (
    CurrentDealIdentity,
    DealIdentityConflict,
    DealIdentityDecision,
    append_deal_identity_decision,
    derive_deal_identity_decision_id,
    derive_source_record_key,
    resolve_deal_for_source_record,
)
from closer_ai.domain.outcome import CurrentOutcome

CO, KOMMO = "agrotalento-001", "kommo"
T1 = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
T3 = datetime(2026, 6, 3, 10, 0, tzinfo=UTC)
DEAL_X = derive_deal_id(CO, KOMMO, "card-a")  # the Deal card-a founds
DEAL_Y = derive_deal_id(CO, KOMMO, "card-z")


def key(card, provider=KOMMO):
    return derive_source_record_key(CO, provider, card)


def dec(card, status, deal_id=None, *, candidates=(), by="automatic", supersedes=None, at=T1,
        provider=KOMMO):
    k = derive_source_record_key(CO, provider, card)
    return DealIdentityDecision(
        identity_decision_id=derive_deal_identity_decision_id(
            k, status, deal_id, candidates, by, supersedes, at
        ),
        company_id=CO, provider=provider, external_record_id=card, status=status,
        deal_id=deal_id, candidate_deal_ids=candidates, decided_by=by,
        supersedes_decision_id=supersedes, created_at=at,
    )


def history(*decisions):
    h = []
    for d in decisions:
        h = append_deal_identity_decision(h, d)
    return h


def test_1_card_that_founds_a_deal_links_to_it_automatically():
    d = dec("card-a", "linked", DEAL_X)
    result = resolve_deal_for_source_record(key("card-a"), history(d))
    assert (result.state, result.deal_id) == ("linked", DEAL_X)


def test_automatic_link_to_another_deal_is_refused():
    with pytest.raises(ValidationError, match="only link a record to the Deal it founds"):
        dec("card-b", "linked", DEAL_X)


def test_2_two_cards_confirmed_as_same_deal():
    a = dec("card-a", "linked", DEAL_X)
    b = dec("card-b", "linked", DEAL_X, by="manual")
    assert resolve_deal_for_source_record(key("card-a"), history(a)).deal_id == DEAL_X
    assert resolve_deal_for_source_record(key("card-b"), history(b)).deal_id == DEAL_X


def test_3_same_name_without_strong_evidence_stays_ambiguous():
    b = dec("card-b", "ambiguous", candidates=(DEAL_X, DEAL_Y))
    result = resolve_deal_for_source_record(key("card-b"), history(b))
    assert (result.state, result.deal_id) == ("ambiguous", None)
    assert set(result.candidate_deal_ids) == {DEAL_X, DEAL_Y}


def test_ambiguous_needs_two_candidates_and_nothing_else_carries_them():
    with pytest.raises(ValidationError, match="at least two"):
        dec("card-b", "ambiguous", candidates=(DEAL_X,))
    with pytest.raises(ValidationError, match="at least two"):
        dec("card-b", "unresolved", candidates=(DEAL_X, DEAL_Y))


def test_4_new_open_card_after_lost_card_is_not_assumed_same_deal():
    new = dec("card-b", "unresolved")
    result = resolve_deal_for_source_record(key("card-b"), history(new))
    assert (result.state, result.deal_id) == ("unresolved", None)


def test_5_explicit_reopen_links_new_card_to_existing_deal():
    unresolved = dec("card-b", "unresolved")
    reopen = dec("card-b", "linked", DEAL_X, by="manual", supersedes=unresolved.identity_decision_id,
                 at=T2)
    assert resolve_deal_for_source_record(key("card-b"), history(unresolved, reopen)).deal_id == DEAL_X


def test_6_and_14_parallel_cards_share_one_deal_and_one_outcome_key():
    a = dec("card-a", "linked", DEAL_X)
    b = dec("card-b", "linked", DEAL_X, by="manual")
    deals = {
        resolve_deal_for_source_record(key("card-a"), history(a)).deal_id,
        resolve_deal_for_source_record(key("card-b"), history(b)).deal_id,
    }
    assert deals == {DEAL_X}
    # the outcome is keyed by deal_id only: one outcome for all linked cards
    assert CurrentOutcome(deal_id=DEAL_X, state="no_assessment").deal_id == DEAL_X


def test_7_automation_card_does_not_create_a_deal():
    bot = dec("card-bot", "unresolved")
    assert resolve_deal_for_source_record(key("card-bot"), history(bot)).deal_id is None
    manual = dec("card-bot", "not_a_deal", by="manual", supersedes=bot.identity_decision_id, at=T2)
    assert resolve_deal_for_source_record(key("card-bot"), history(bot, manual)).state == "not_a_deal"


def test_not_a_deal_is_manual_only():
    with pytest.raises(ValidationError, match="manual decision"):
        dec("card-bot", "not_a_deal")


def test_8_same_record_ingested_twice_is_idempotent():
    d = dec("card-a", "linked", DEAL_X)
    h = history(d)
    assert append_deal_identity_decision(h, d) == h
    rerun = dec("card-a", "linked", DEAL_X, supersedes=d.identity_decision_id, at=T2)
    assert append_deal_identity_decision(h, rerun) == h  # same result: no new logical decision


def test_9_same_id_different_payload_is_hard_error():
    d = dec("card-a", "linked", DEAL_X)
    tampered = d.model_copy(update={"deal_id": DEAL_Y})
    with pytest.raises(ValueError, match="different payload"):
        append_deal_identity_decision(history(d), tampered)


def test_9_competing_decision_on_same_record_is_cas_conflict():
    root = dec("card-b", "unresolved")
    first = dec("card-b", "linked", DEAL_X, by="manual", supersedes=root.identity_decision_id, at=T2)
    second = dec("card-b", "not_a_deal", by="manual", supersedes=root.identity_decision_id, at=T3)
    h = history(root, first)
    with pytest.raises(DealIdentityConflict, match="stale write"):
        append_deal_identity_decision(h, second)


def test_10_providers_never_collide():
    assert key("123", "kommo") != key("123", "pipedrive")
    assert key("123", "kommo") != derive_deal_id(CO, "kommo", "123")


def test_11_human_resolves_ambiguity_and_it_persists():
    amb = dec("card-b", "ambiguous", candidates=(DEAL_X, DEAL_Y))
    human = dec("card-b", "linked", DEAL_Y, by="manual", supersedes=amb.identity_decision_id, at=T2)
    result = resolve_deal_for_source_record(key("card-b"), history(amb, human))
    assert (result.state, result.deal_id) == ("linked", DEAL_Y)


def test_12_automation_cannot_override_human():
    human = dec("card-b", "linked", DEAL_Y, by="manual")
    auto = dec("card-b", "unresolved", supersedes=human.identity_decision_id, at=T2)
    h = history(human)
    with pytest.raises(DealIdentityConflict, match="manual"):
        append_deal_identity_decision(h, auto)
    # a history written elsewhere with automatic over manual is a conflict, not a winner
    assert resolve_deal_for_source_record(key("card-b"), [human, auto]).state == "conflict"


def test_13_orphan_record_is_legitimate():
    assert resolve_deal_for_source_record(key("card-o"), []).state == "no_decision"
    assert resolve_deal_for_source_record(key("card-o"), history(dec("card-o", "unresolved"))).state == "unresolved"


def test_forked_history_is_conflict():
    root = dec("card-b", "unresolved")
    x = dec("card-b", "linked", DEAL_X, by="manual", supersedes=root.identity_decision_id, at=T2)
    y = dec("card-b", "linked", DEAL_Y, by="manual", supersedes=root.identity_decision_id, at=T3)
    result = resolve_deal_for_source_record(key("card-b"), [root, x, y])
    assert (result.state, result.deal_id) == ("conflict", None)
    with pytest.raises(DealIdentityConflict, match="linear"):
        append_deal_identity_decision(
            [root, x, y], dec("card-b", "unresolved", by="manual", supersedes=x.identity_decision_id, at=T3)
        )


def test_decisions_of_another_record_are_rejected():
    with pytest.raises(ValueError, match="another source record"):
        resolve_deal_for_source_record(key("card-a"), [dec("card-b", "unresolved")])


def test_created_at_never_orders_the_chain():
    first = dec("card-b", "unresolved", at=T3)
    second = dec("card-b", "linked", DEAL_X, by="manual", supersedes=first.identity_decision_id, at=T1)
    assert resolve_deal_for_source_record(key("card-b"), list(reversed(history(first, second)))).deal_id == DEAL_X


def test_linked_requires_exactly_one_deal():
    with pytest.raises(ValidationError, match="deal_id is set if and only if"):
        dec("card-a", "linked", None)
    with pytest.raises(ValidationError, match="deal_id is set if and only if"):
        dec("card-a", "unresolved", DEAL_X)


def test_forged_decision_id_is_rejected():
    with pytest.raises(ValidationError, match="identity_decision_id"):
        DealIdentityDecision(
            identity_decision_id="did_forged", company_id=CO, provider=KOMMO,
            external_record_id="card-a", status="unresolved", decided_by="manual", created_at=T1,
        )


def test_current_identity_invariants():
    with pytest.raises(ValidationError):
        CurrentDealIdentity(source_record_key=key("c"), state="unresolved", deal_id=DEAL_X,
                            decision_id="did_x")
    with pytest.raises(ValidationError):
        CurrentDealIdentity(source_record_key=key("c"), state="conflict", decision_id="did_x")


def test_self_referencing_decision_is_rejected():
    # the id hashes supersedes_decision_id, so a decision naming itself as parent can only be
    # a forged record, and it fails validation
    with pytest.raises(ValidationError):
        DealIdentityDecision(
            identity_decision_id="did_self", company_id=CO, provider=KOMMO,
            external_record_id="card-a", status="unresolved", decided_by="manual",
            supersedes_decision_id="did_self", created_at=T1,
        )
