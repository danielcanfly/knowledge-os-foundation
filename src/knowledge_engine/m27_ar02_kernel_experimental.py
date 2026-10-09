"""EXPERIMENTAL_NO_EXTERNAL_DISPATCH: sequential in-memory proof, not authority."""

from copy import deepcopy


class Denied(Exception):
    pass

class Kernel:
    def __init__(self, budget):
        if type(budget) is not int or budget < 0:
            raise Denied("budget")
        self.budget = budget
        self.runs = {}
        self.network_requests = 0

    def create(self, run, tenant):
        if not run or not tenant or run in self.runs:
            raise Denied("identity")
        self.runs[run] = dict(tenant=tenant, head=0, epoch=1, terminal=False,
                              spent=0, reserved={}, charges={}, intents={},
                              approvals=set(), claims=set(), unknown=set())

    def _state(self, run, tenant):
        state = self.runs.get(run)
        if not state or state["tenant"] != tenant:
            raise Denied("tenant")
        return state

    def read(self, run, tenant):
        return deepcopy(self._state(run, tenant))

    def cas(self, run, tenant, head, epoch):
        state = self._state(run, tenant)
        if state["terminal"] or state["head"] != head or state["epoch"] != epoch:
            raise Denied("stale or terminal")
        state["head"] += 1
        return state["head"]

    def takeover(self, run, tenant, head):
        state = self._state(run, tenant)
        self.cas(run, tenant, head, state["epoch"])
        state["epoch"] += 1

    def reserve(self, run, tenant, head, epoch, key, amount):
        state = self._state(run, tenant)
        if (not key or key in state["reserved"] or type(amount) is not int
                or amount < 0 or state["spent"] + sum(state["reserved"].values())
                + amount > self.budget):
            raise Denied("reservation")
        self.cas(run, tenant, head, epoch)
        state["reserved"][key] = amount

    def charge(self, run, tenant, head, epoch, reserve_id, charge_id, amount):
        state = self._state(run, tenant)
        if not charge_id or type(amount) is not int or amount < 0:
            raise Denied("charge")
        if charge_id in state["charges"]:
            if state["charges"][charge_id] != (reserve_id, amount):
                raise Denied("charge id conflict")
            return False
        if reserve_id not in state["reserved"] or amount > state["reserved"][reserve_id]:
            raise Denied("insufficient reservation")
        self.cas(run, tenant, head, epoch)
        state["spent"] += amount
        del state["reserved"][reserve_id]
        state["charges"][charge_id] = (reserve_id, amount)
        return True

    def intent(self, run, tenant, head, epoch, intent_id, digest, approval, trusted=False):
        state = self._state(run, tenant)
        if (not trusted or not intent_id or not digest or not approval
                or intent_id in state["intents"] or approval in state["approvals"]):
            raise Denied("untrusted or duplicate intent")
        self.cas(run, tenant, head, epoch)
        state["intents"][intent_id] = (digest, approval)
        state["approvals"].add(approval)

    def claim(self, run, tenant, head, epoch, intent_id, digest, trusted=False):
        state = self._state(run, tenant)
        if (not trusted or intent_id not in state["intents"]
                or state["intents"][intent_id][0] != digest
                or intent_id in state["claims"]):
            raise Denied("untrusted or duplicate claim")
        self.cas(run, tenant, head, epoch)
        state["claims"].add(intent_id)

    def possible_send(self, run, tenant, head, epoch, intent_id):
        state = self._state(run, tenant)
        if intent_id not in state["claims"] or intent_id in state["unknown"]:
            raise Denied("unclaimed/replayed")
        self.cas(run, tenant, head, epoch)
        state["unknown"].add(intent_id)
        return "UNKNOWN_EFFECT"  # no external dispatch code exists

    def terminal(self, run, tenant, head, epoch, verified_head, trusted=False):
        state = self._state(run, tenant)
        if not trusted or verified_head != head or state["unknown"]:
            raise Denied("untrusted/stale verifier or unknown effect")
        self.cas(run, tenant, head, epoch)
        state["terminal"] = True
