"""C1 owner-firstparty M26 production-parity E2E evidence gate.

This is a SEPARATE product-profile acceptance from mandatory signed Product
C1. Does not alter, replace, bypass or sign the external-authority ABI. It
accepts ONLY physical OS Client/Provider/source journal evidence from the
one permitted firstparty bounded run; never model/source fixtures as proof.

Not a standalone release or 523-case benchmark certificate.
"""
from __future__ import annotations
import hashlib, json, os, re, stat
from pathlib import Path

ABI="m27.c1.m26-owner-production-parity-evidence/v1"
CLOUDFLARE="@cf/openai/gpt-oss-120b"
CLAIMS=("execution_governance_verification","policy_engine_enforcement")
MAX_LOG=1024*1024
class Rejected(ValueError):pass

def check(test,why):
    if not test:raise Rejected(why)
def digest(raw):return hashlib.sha256(raw).hexdigest()

def owned_private(path):
    path=Path(path)
    st=path.lstat()
    check(stat.S_ISREG(st.st_mode) and not path.is_symlink()
          and st.st_uid==os.geteuid() and
          not (stat.S_IMODE(st.st_mode) & 0o077) and
          0<st.st_size<=MAX_LOG,"M26_EVIDENCE_OWNER_PRIVATE_FILE_REQUIRED")
    return path.read_bytes()

def parse_json(path):
    return json.loads(owned_private(path))
def parse_jsonl(path):
    raw=owned_private(path)
    out=[json.loads(x) for x in raw.splitlines()]
    check(out and all(type(x) is dict for x in out),
          "M26_PROVIDER_JOURNAL_INVALID")
    return out

def evaluate(evidence_dir, *, head, tree, real_run=True,
             allow_synthetic=False):
    """Require real-run files; never produce PASS for a test/mock claim.

    The external caller must separately pin HEAD/TREE clean + source corpus
    exact actual bytes. This function rejects not-the-same-run evidence.
    """
    e=Path(evidence_dir).resolve(strict=True)
    check(type(head) is str and re.fullmatch("[0-9a-f]{40}",head) and
          type(tree) is str and re.fullmatch("[0-9a-f]{40}",tree),
          "M26_C1_GIT_SOURCE_IDENTITY_REQUIRED")
    check(real_run is True,"M26_FIXTURE_NOT_ELIGIBLE_FOR_PRODUCT")
    run=parse_json(e/"C1_REAL_MINIMAX_DEV_RUN_RESULT.json")
    c=parse_json(e/"C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json")
    log=parse_jsonl(e/"C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl")
    source_journal=parse_jsonl(e/"C1_REAL_TASK_JOURNAL.jsonl")
    prepared=run.get("source_prepared")
    check(type(prepared) is dict and
          prepared.get("prepared_source_count")==2 and
          prepared.get("source_byte_verified_local") is True and
          isinstance(prepared.get("task_contract_sha256"),str) and
          re.fullmatch("[0-9a-f]{64}",prepared["task_contract_sha256"]) and
          isinstance(prepared.get("source_proof_sha256"),str) and
          re.fullmatch("[0-9a-f]{64}",prepared["source_proof_sha256"]),
          "M26_REAL_A05_SOURCE_TASK_REQUIRED")
    request=prepared.get("request_id")
    check(type(request) is str and
          re.fullmatch("[0-9a-f]{48}",request),
          "M26_SINGLE_TASK_REQUEST_ID_INVALID")
    check(len(source_journal)==1 and
          source_journal[0].get("event")==
              "real_a05_source_and_task_prepared_NOT_PROVIDER" and
          source_journal[0].get("request_id")==request and
          source_journal[0].get("task_sha256")==
              prepared["task_contract_sha256"] and
          source_journal[0].get("source_proof_sha256")==
              prepared["source_proof_sha256"] and
          source_journal[0].get("provider_called") is False and
          source_journal[0].get("product_qualified") is False,
          "M26_REAL_SOURCE_TASK_JOURNAL_MISMATCH")
    # Genuine scoped PASS can only be issued *inside* the actual server's
    # running OS process, not by opening a file copied from a prior task.
    # Synthetic unit tests use an explicit TEST_ONLY mode, which never PASSes.
    if not allow_synthetic:
        check(run.get("parent_native_server_pid")==os.getpid(),
              "M26_ONLY_ACTIVE_REAL_OS_SERVER_MAY_ISSUE_PARITY_RESULT")
    check(run.get("current_source_head")==head and
          run.get("current_source_tree")==tree and
          run.get("source_clean_at_e2e_execution") is True,
          "M26_ACTUAL_RUN_SOURCE_HEAD_TREE_NOT_BOUND")
    check(run.get("provider_mode")=="m26-parity-direct" and
          run.get("actual_real_provider_call_count")==1 and
          run.get("real_provider_done_observed") is True and
          run.get("client_process_exit")==0 and
          run.get("local_native_ack_count")==2 and
          run.get("formal_product_pass") is False,
          "M26_AUTHENTIC_CLOUDFLARE_PRIMARY_NOT_COMPLETED")
    check(type(c) is dict and type(c.get("client_pid")) is int and
          c["client_pid"]!=run.get("parent_native_server_pid") and
          type(c.get("receipts")) is list,
          "M26_INDEPENDENT_NATIVE_OS_CLIENT_RECEIPTS_REQUIRED")
    receipts=c["receipts"]
    check([x.get("event") for x in receipts]==
          ["request_start","answer_text","answer_text","terminal"],
          "M26_NATIVE_RECEIPT_SEQUENCE_INVALID")
    first,second,terminal=receipts[1:]
    for j,item in enumerate((first,second)):
        check(item.get("request_id")==request and
              item.get("task_sha256")==prepared["task_contract_sha256"] and
              item.get("ack_http_status")==200 and
              item.get("citation_count")==1 and
              item.get("source_verifier_os_pid") not in
              (None,c["client_pid"],run.get("parent_native_server_pid")),
              "M26_VERIFIED_SOURCE_CLIENT_ACK_INCOMPLETE")
    check(first.get("observed_before_provider_done") is True and
          terminal.get("request_id")==request and
          terminal.get("full_cited_final") is True and
          terminal.get("citation_count")==2 and
          terminal.get("real_model_calls")==1 and
          terminal.get("scope_product_pass") is False,
          "M26_CLIENT_PRETERMINAL_CITATION_OR_FINAL_REQUIRED")
    check(set(terminal.get("citations",{}))==set(CLAIMS) and
          terminal.get("answer_sha256") and
          re.fullmatch("[0-9a-f]{64}",terminal["answer_sha256"]),
          "M26_TWO_A05_CLAIMS_NOT_CITED")
    for item in receipts:
        check(item.get("request_id")==request,
              "M26_CROSS_TASK_CLIENT_RECEIPT_DENIED")
    # Must be the actual generated provider text and verified OS/native events.
    starts=[x for x in log if x.get("event")=="actual_provider_started"]
    checks=[x for x in log if x.get("event")=="real_provider_identity"]
    deltas=[x for x in log if x.get("event")=="actual_provider_raw_delta"]
    delivered=[x for x in log if x.get("event")=="native_delivery_answer_text"]
    acks=[x for x in log if x.get("event")=="native_client_local_ack"]
    done=[x for x in log if x.get("event")=="actual_provider_done"]
    check(len(starts)==len(checks)==len(done)==1 and
          starts[0].get("provider")==CLOUDFLARE and
          checks[0].get("model")==CLOUDFLARE and
          starts[0].get("request_id")==request and
          len(deltas)>0 and len(deltas)<=128 and
          [x.get("sequence") for x in deltas]==list(range(1,len(deltas)+1)) and
          len(delivered)==len(acks)==2,
          "M26_REAL_CLOUDFLARE_STREAM_AND_ACK_JOURNAL_REQUIRED")
    for item in deltas:
        check(type(item.get("text")) is str and item["text"] and
              item.get("sha256")==digest(item["text"].encode()),
              "M26_PROVIDER_RAW_MODEL_DELTA_SHA_MISMATCH")
    for i,claim in enumerate(CLAIMS):
        check(delivered[i].get("request_id")==request and
              delivered[i].get("text_sha256")==receipts[i+1].get("model_text_sha256") and
              acks[i].get("claim_id")==claim and
              acks[i].get("request_id")==request and
              acks[i].get("text_sha256")==receipts[i+1].get("model_text_sha256") and
              delivered[i].get("source_cited") is True,
              "M26_REAL_MODEL_TEXT_CLIENT_PROOF_MISMATCH")
        # A06/A07: all three physical sources independently retain the
        # nonce challenge hash + exact 5-field ACK binding. Client stores
        # the raw POST body's digest and the accepting Server independently
        # hashes that received HTTP body. No plaintext nonce in evidence.
        client_row=receipts[i+1]
        for key in ("challenge_sha256","ack_binding_sha256",
                    "ack_request_body_sha256"):
            values=[client_row.get(key),acks[i].get(key)]
            if key!="ack_request_body_sha256":
                values.append(delivered[i].get(key))
            check(all(type(v) is str and
                      re.fullmatch("[0-9a-f]{64}",v) for v in values) and
                  len(set(values))==1,
                  "M26_ACK_CHALLENGE_BINDING_CUSTODY_MISSING_OR_MISMATCH")
        check(client_row.get("claim_id")==claim and
              delivered[i].get("claim_id")==claim and
              delivered[i].get("task_sha256")==prepared["task_contract_sha256"] and
              acks[i].get("task_sha256")==prepared["task_contract_sha256"],
              "M26_ACK_BINDING_TASK_OR_CLAIM_MISMATCH")
    check(receipts[1].get("challenge_sha256")!=
          receipts[2].get("challenge_sha256"),
          "M26_REUSED_ACK_CHALLENGE_DENIED")
    check(
        type(acks[0].get("at_ns")) is int and
        type(done[0].get("at_ns")) is int and
        starts[0]["at_ns"]<acks[0]["at_ns"]<done[0]["at_ns"] and
        delivered[0]["at_ns"]<=acks[0]["at_ns"] and
        done[0].get("first_client_ack_before_done") is True,
        "M26_FIRST_VERIFIED_CLIENT_ACK_NOT_PRETERMINAL")
    check(not any(x.get("event")=="live_dev_fail_closed" for x in log),
          "M26_ERROR_OR_PARTIAL_RUN_CANNOT_PASS")
    text="".join(x["text"] for x in deltas)
    # Physically Client-ACKed sentences must exist in original model text.
    candidate_lines=[line.strip() for line in text.splitlines()
                      if line.strip()]
    check(len(candidate_lines)==2 and
          all(line.endswith(".") for line in candidate_lines) and
          [digest(line.encode()) for line in candidate_lines]==
          [first.get("model_text_sha256"),
           second.get("model_text_sha256")] and
          digest(" ".join(candidate_lines).encode())==
          terminal.get("answer_sha256"),
          "M26_SUBSTANTIVE_MODEL_TEXT_NOT_IN_RAW_DELTAS")
    return {"abi":ABI,
        "status":("TEST_ONLY_SYNTHETIC_EVIDENCE_STRUCTURE_PASS"
            if allow_synthetic else
            "C1_OWNER_FIRSTPARTY_M26_NONPROD_E2E_PARITY_PASS"),
        "formal_independently_signed_product_pass":False,
        "production_release_qualified":False,
        "current_head":head,"current_tree":tree,
        "request_id":request,"task_sha256":prepared["task_contract_sha256"],
        "source_proof_sha256":prepared["source_proof_sha256"],
        "model":CLOUDFLARE,"real_delta_count":len(deltas),
        "real_provider_stream_sha256":digest(text.encode()),
        "native_client_pid":c["client_pid"],
        "two_real_client_acks":True,
        "first_ack_preterminal":True,
        "full_cited_final":True,"citations":terminal["citations"],
        "original_evidence_file_sha256":{
            name:digest(owned_private(e/name)) for name in
            ("C1_REAL_MINIMAX_DEV_RUN_RESULT.json",
             "C1_INDEPENDENT_OS_NATIVE_CLIENT_RECEIPTS.json",
             "C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl",
             "C1_REAL_TASK_JOURNAL.jsonl")},
        "not_a_523_case_benchmark":True}
