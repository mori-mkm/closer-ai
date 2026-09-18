from datetime import UTC, datetime

from synthetic_calls import raw_call

from closer_ai.domain.deal import derive_deal_id
from closer_ai.domain.matching import CallDealMatcher, ExactExternalIdMatcher
from closer_ai.normalization.normalize import normalize_call

_CREATED_AT = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def _call(source_id="synth-call-0001"):
    return normalize_call(raw_call(source_id=source_id))


def _deal(external_id, **overrides):
    company_id = overrides.pop("company_id", "synthco-001")
    source = overrides.pop("source", "synthetic")
    from closer_ai.domain.deal import Deal

    return Deal(
        deal_id=derive_deal_id(company_id, source, external_id),
        company_id=company_id,
        source=source,
        external_id=external_id,
        current_stage=overrides.pop("current_stage", "negotiation"),
        outcome=overrides.pop("outcome", "open"),
        created_at=overrides.pop("created_at", _CREATED_AT),
        **overrides,
    )


def test_exact_external_id_matcher_implements_protocol():
    assert isinstance(ExactExternalIdMatcher(), CallDealMatcher)


def test_single_exact_match():
    call = _call(source_id="synth-call-0001")
    deal = _deal(external_id="synth-call-0001")
    results = ExactExternalIdMatcher().match(call, [deal, _deal(external_id="unrelated")])
    assert len(results) == 1
    assert results[0].status == "matched"
    assert results[0].deal_id == deal.deal_id
    assert results[0].confidence_level == "high"


def test_no_candidates_yields_unmatched():
    call = _call(source_id="synth-call-0001")
    results = ExactExternalIdMatcher().match(call, [_deal(external_id="unrelated")])
    assert len(results) == 1
    assert results[0].status == "unmatched"
    assert results[0].deal_id is None


def test_empty_candidate_list_yields_unmatched():
    call = _call(source_id="synth-call-0001")
    results = ExactExternalIdMatcher().match(call, [])
    assert len(results) == 1
    assert results[0].status == "unmatched"


def test_tied_candidates_are_ambiguous_never_silently_picked():
    # duplicate external_id across two deals is a data-quality edge case, but the matcher
    # must never silently pick a "winner" — this is the critical invariant of the whole task
    call = _call(source_id="synth-call-0001")
    deal_a = _deal(external_id="synth-call-0001", company_id="synthco-001", source="synthetic")
    deal_b = _deal(external_id="synth-call-0001", company_id="synthco-002", source="synthetic")
    results = ExactExternalIdMatcher().match(call, [deal_a, deal_b])
    assert len(results) == 2
    assert {r.status for r in results} == {"ambiguous"}
    assert {r.deal_id for r in results} == {deal_a.deal_id, deal_b.deal_id}


def test_match_results_are_valid_and_traceable():
    call = _call(source_id="synth-call-0001")
    deal = _deal(external_id="synth-call-0001")
    result = ExactExternalIdMatcher().match(call, [deal])[0]
    assert result.call_id == call.call_id
    assert result.evidence[0].signal == "external_id_exact"
    assert result.evidence[0].matched is True


def test_matcher_never_raises_on_no_match():
    call = _call(source_id="synth-call-0001")
    # must not raise even with a completely unrelated candidate set
    results = ExactExternalIdMatcher().match(call, [_deal(external_id="x"), _deal(external_id="y")])
    assert len(results) == 1
    assert results[0].status == "unmatched"


def test_duplicate_deal_id_candidates_do_not_produce_false_ambiguity():
    # a caller passing the same deal twice (e.g. a duplicated upstream join) must never be
    # treated as two distinct plausible candidates — that would be false ambiguity from a
    # caller bug, the mirror image of "silently pick a winner" this contract exists to prevent
    call = _call(source_id="synth-call-0001")
    deal = _deal(external_id="synth-call-0001")
    results = ExactExternalIdMatcher().match(call, [deal, deal])
    assert len(results) == 1
    assert results[0].status == "matched"
    assert results[0].deal_id == deal.deal_id
