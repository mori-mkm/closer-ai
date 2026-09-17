from closer_ai.normalization.ids import derive_call_id, derive_segment_id


def test_call_id_deterministic_same_input():
    a = derive_call_id("synthco-001", "synthetic", "synth-call-0001")
    b = derive_call_id("synthco-001", "synthetic", "synth-call-0001")
    assert a == b


def test_call_id_differs_by_source_id():
    a = derive_call_id("synthco-001", "synthetic", "synth-call-0001")
    b = derive_call_id("synthco-001", "synthetic", "synth-call-0002")
    assert a != b


def test_call_id_no_ambiguous_concatenation_collision():
    a = derive_call_id("AB", "synthetic", "C")
    b = derive_call_id("A", "synthetic", "BC")
    assert a != b


def test_call_id_does_not_embed_input():
    call_id = derive_call_id("synthco-001", "synthetic", "synth-call-0001")
    assert "synthco-001" not in call_id
    assert "synth-call-0001" not in call_id


def test_segment_id_deterministic_same_input():
    a = derive_segment_id("call_abc", 0)
    b = derive_segment_id("call_abc", 0)
    assert a == b


def test_segment_id_differs_by_index():
    a = derive_segment_id("call_abc", 0)
    b = derive_segment_id("call_abc", 1)
    assert a != b


def test_segment_id_differs_by_call_id():
    a = derive_segment_id("call_abc", 0)
    b = derive_segment_id("call_xyz", 0)
    assert a != b
