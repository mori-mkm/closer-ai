import pytest
from pydantic import ValidationError

from closer_ai.domain.lead import Lead, derive_lead_id


def _lead(**overrides):
    company_id = overrides.pop("company_id", "agrotalento-001")
    source = overrides.pop("source", "kommo")
    external_id = overrides.pop("external_id", "contact-1")
    lead_id = overrides.pop("lead_id", derive_lead_id(company_id, source, external_id))
    return Lead(
        lead_id=lead_id,
        company_id=company_id,
        source=source,
        external_id=external_id,
        **overrides,
    )


def test_lead_minimal_valid():
    lead = _lead()
    assert lead.name is None
    assert lead.email is None
    assert lead.metadata == {}


def test_lead_no_identifying_field_required():
    # Lead's job is to hold whatever the source gave it; completeness is CallDealMatch's concern
    lead = _lead(name=None, email=None, phone=None)
    assert lead.lead_id


def test_lead_id_matches_derivation():
    lead = _lead()
    assert lead.lead_id == derive_lead_id("agrotalento-001", "kommo", "contact-1")


def test_lead_id_rejects_mismatch():
    with pytest.raises(ValidationError):
        _lead(lead_id="lead_wrong")


@pytest.mark.parametrize("field", ["company_id", "source", "external_id"])
def test_lead_rejects_blank_identity_fields(field):
    with pytest.raises(ValidationError):
        _lead(**{field: "  "})


def test_lead_is_deterministic():
    first = _lead()
    second = _lead()
    assert first == second
    assert first.lead_id == second.lead_id


def test_lead_pii_does_not_affect_id():
    a = _lead(name="Ana Souza", email="ana@agrotalento.example", phone="+55 11 90000-0000")
    b = _lead(name="Bruno Lima", email="bruno@agrotalento.example", phone="+55 11 90000-0001")
    assert a.lead_id == b.lead_id  # same (company_id, source, external_id), different PII


def test_lead_different_external_id_no_collision():
    a = _lead(external_id="contact-1")
    b = _lead(external_id="contact-2")
    assert a.lead_id != b.lead_id


def test_lead_frozen():
    lead = _lead()
    with pytest.raises(ValidationError):
        lead.name = "changed"  # type: ignore[misc]


def test_lead_company_name_distinct_from_tenant_company_id():
    lead = _lead(company_name="AgroTalento LTDA")
    assert lead.company_name == "AgroTalento LTDA"
    assert lead.company_id == "agrotalento-001"
    assert lead.company_name != lead.company_id
