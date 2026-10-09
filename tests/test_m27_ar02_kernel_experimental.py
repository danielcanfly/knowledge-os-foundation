import pytest

from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel


def fresh(budget=10):
    k = Kernel(budget)
    k.create("r", "t")
    return k

def test_two_writers_epoch_and_tenant():
    k = fresh()
    assert k.cas("r", "t", 0, 1) == 1
    with pytest.raises(Denied):
        k.cas("r", "t", 0, 1)
    k.takeover("r", "t", 1)
    with pytest.raises(Denied):
        k.cas("r", "t", 2, 1)
    with pytest.raises(Denied):
        k.read("r", "wrong")
    assert k.network_requests == 0

def test_zero_and_double_reservations():
    k = fresh(0)
    k.reserve("r", "t", 0, 1, "z", 0)
    with pytest.raises(Denied):
        k.reserve("r", "t", 1, 1, "p", 1)
    k = fresh()
    k.reserve("r", "t", 0, 1, "a", 7)
    with pytest.raises(Denied):
        k.reserve("r", "t", 1, 1, "b", 4)
    k.reserve("r", "t", 1, 1, "b", 3)
    assert sum(k.read("r", "t")["reserved"].values()) == 10

def test_charge_idempotence_conflict():
    k = fresh()
    k.reserve("r", "t", 0, 1, "q", 5)
    assert k.charge("r", "t", 1, 1, "q", "c", 5)
    assert k.charge("r", "t", 2, 1, "q", "c", 5) is False
    with pytest.raises(Denied):
        k.charge("r", "t", 2, 1, "q", "c", 4)
    assert k.read("r", "t")["spent"] == 5

def test_intent_identity_approval_consumption():
    k = fresh()
    with pytest.raises(Denied):
        k.intent("r", "t", 0, 1, "i", "digest", "user-token")
    assert not k.read("r", "t")["intents"]
    k.intent("r", "t", 0, 1, "i", "digest", "approval", trusted=True)
    with pytest.raises(Denied):
        k.intent("r", "t", 1, 1, "j", "changed", "approval", trusted=True)
    with pytest.raises(Denied):
        k.claim("r", "t", 1, 1, "i", "wrong", trusted=True)
    with pytest.raises(Denied):
        k.claim("r", "t", 1, 1, "i", "digest")
    k.claim("r", "t", 1, 1, "i", "digest", trusted=True)
    with pytest.raises(Denied):
        k.claim("r", "t", 2, 1, "i", "digest", trusted=True)

def test_t1_t2_t3_crash_simulation():
    k = fresh()
    assert not k.read("r", "t")["intents"]  # pre-T1
    k.intent("r", "t", 0, 1, "i", "digest", "a", trusted=True)  # T1
    with pytest.raises(Denied):
        k.possible_send("r", "t", 1, 1, "i")  # before claim T2
    k.claim("r", "t", 1, 1, "i", "digest", trusted=True)  # T2
    assert not k.read("r", "t")["unknown"]
    assert k.possible_send("r", "t", 2, 1, "i") == "UNKNOWN_EFFECT"  # T3
    with pytest.raises(Denied):
        k.possible_send("r", "t", 3, 1, "i")
    with pytest.raises(Denied):
        k.terminal("r", "t", 3, 1, 3, trusted=True)
    assert k.network_requests == 0

def test_stale_verifier_terminal_immutability():
    k = fresh()
    k.cas("r", "t", 0, 1)
    with pytest.raises(Denied):
        k.terminal("r", "t", 1, 1, 0, trusted=True)
    with pytest.raises(Denied):
        k.terminal("r", "t", 1, 1, 1)
    k.terminal("r", "t", 1, 1, 1, trusted=True)
    with pytest.raises(Denied):
        k.cas("r", "t", 2, 1)
    assert k.network_requests == 0


def test_charge_id_cannot_be_reused_for_another_reservation():
    k = fresh()
    k.reserve("r", "t", 0, 1, "a", 3)
    k.reserve("r", "t", 1, 1, "b", 3)
    assert k.charge("r", "t", 2, 1, "a", "same-charge", 3)
    with pytest.raises(Denied):
        k.charge("r", "t", 3, 1, "b", "same-charge", 3)
    assert k.read("r", "t")["reserved"]["b"] == 3


def test_wrong_tenant_cannot_cas_head():
    k = fresh()
    with pytest.raises(Denied):
        k.cas("r", "wrong", 0, 1)
    assert k.read("r", "t")["head"] == 0


def test_read_snapshot_cannot_modify_journal_state():
    k = fresh()
    snapshot = k.read("r", "t")
    snapshot["head"] = 77
    snapshot["approvals"].add("forged")
    assert k.cas("r", "t", 0, 1) == 1
    assert not k.read("r", "t")["approvals"]
