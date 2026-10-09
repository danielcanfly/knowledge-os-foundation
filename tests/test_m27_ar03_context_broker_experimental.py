"""All coverage is synthetic, not production authorization verification."""

import pytest

from knowledge_engine.m27_ar03_context_broker_experimental import (
    Candidate,
    GrantFixture,
    Request,
    preserve_native_pin,
    select,
)

D = "a" * 64


def request(**updates):
    values = dict(
        tenant="t",
        principal="p",
        purpose="qa",
        scopes=frozenset({"s"}),
        now=100,
        tokens=2,
        cost=3,
        freshness=20,
    )
    return Request(**(values | updates))


def grant(**updates):
    values = dict(
        tenant="t",
        principal="p",
        purpose="qa",
        scopes=frozenset({"s"}),
        expires=200,
        externally_authenticated=True,
    )
    return GrantFixture(**(values | updates))


def candidate(**updates):
    values = dict(
        scope="s",
        source_id="x",
        revision="r1",
        digest=D,
        tenant="t",
        principals=frozenset({"p"}),
        purpose="qa",
        expires=150,
        retrieved=95,
        tokens=2,
        cost=3,
    )
    return Candidate(**(values | updates))


def test_no_verified_authority():
    assert not select(request(), (candidate(),)).selected
    assert not select(request(), (candidate(),), grant(externally_authenticated=False)).selected
    assert not select(request(), (candidate(),), grant(principal="x")).selected


@pytest.mark.parametrize(
    "change",
    [
        {"tenant": "other"},
        {"principals": frozenset({"other"})},
        {"purpose": "other"},
        {"scope": "other"},
    ],
)
def test_c01_isolation(change):
    result = select(request(), (candidate(**change),), grant())
    assert not result.selected and len(result.omissions) == 1
    assert "source_id" not in repr(result.omissions)


@pytest.mark.parametrize(
    "change",
    [
        {"revoked": True},
        {"consent_expires": 100},
        {"consent_expires": 99},
    ],
)
def test_c02_revocation(change):
    assert not select(request(), (candidate(**change),), grant()).selected


def test_c04_taint_remains_data():
    assert select(request(), (candidate(tainted=True),), grant()).selected[0].tainted


def test_c05_native_pin():
    assert preserve_native_pin("id", D, "id", D, True) == "id"
    assert preserve_native_pin("id", D, "wrong", D, True) is None
    assert preserve_native_pin("id", D, "id", "b" * 64, True) is None
    assert preserve_native_pin("id", D, "id", D) is None


@pytest.mark.parametrize(
    "change",
    [
        {"revision": ""},
        {"expires": 100},
        {"retrieved": 79},
    ],
)
def test_c06_revision_ttl(change):
    assert not select(request(), (candidate(**change),), grant()).selected


def test_c08_absolute_inclusive_budget_and_missing_price():
    assert select(request(tokens=0, cost=0), (candidate(tokens=0, cost=0),), grant()).selected
    assert not select(request(tokens=0), (candidate(),), grant()).selected
    assert not select(request(cost=0), (candidate(),), grant()).selected
    assert not select(request(), (candidate(cost=None),), grant()).selected
    assert select(request(), (candidate(),), grant()).cost == 3


def test_c09_conflicting_source_digest():
    result = select(request(tokens=4, cost=6), (candidate(), candidate(digest="b" * 64)), grant())
    assert len(result.selected) == 1
    assert ("s", "invalid_digest") in result.omissions


def test_c10_offsets_and_c11_unsigned_skill():
    assert not select(request(), (candidate(citation_offsets_safe=False),), grant()).selected
    assert not select(request(), (candidate(skill=True, signed=False),), grant()).selected


def test_c12_synthetic_native_forbidden():
    assert not select(request(), (candidate(synthetic_native=True),), grant()).selected


def test_expiration_and_budget_validation():
    assert select(request(), (candidate(expires=110),), grant()).expires == 110
    assert not select(request(), (candidate(),), grant(expires=100)).selected
    with pytest.raises(ValueError):
        select(request(tokens=-1), ())
