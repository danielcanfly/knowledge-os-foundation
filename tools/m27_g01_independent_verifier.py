"""Separate-process byte-span entailment verifier, narrow-domain test proof only.

Independence = distinct OS process and own source reread. NOT an external signed
rights grant, licensed Provider identity, or general semantic entailment verifier.
"""
import hashlib
import json
import pathlib
import sys

SOURCE_SHA = "137009ea0618710222bef118c3ca258dfe98b5f8911e8dc588ac154dd4d17fb9"
SUPPORTED = {
    "cache_initial_mode": {
        "span": (6582, 6635),
        "byte_text": "Initial semantic answer cache remains OFF in Nonprod.",
        "answers": {
            "the semantic answer cache is off in nonprod initially.",
            "the initial nonprod semantic answer cache mode is off.",
            "initially, the semantic answer cache is off in nonprod.",
        },
    },
    "macbook_first_tool": {
        "span": (5145, 5212),
        "byte_text": "All new engineering uses Remote Desktop Commander first on MacBook.",
        "answers": {
            "remote desktop commander is first for engineering on macbook.",
            "the first engineering tool on macbook is remote desktop commander.",
        },
    },
}

def main():
    try:
        req = json.load(sys.stdin)
        if set(req) != {"source_path", "source_sha256", "tenant", "principal",
                        "obligation", "answer", "citation"}:
            raise ValueError("UNEXPECTED_VERIFIER_FIELDS")
        obligation = req["obligation"]
        item = SUPPORTED[obligation]
        if req["tenant"] != "owner-nonprod" or req["principal"] != "owner-qa":
            raise ValueError("TENANT_PRINCIPAL_DENIED")
        source = pathlib.Path(req["source_path"])
        raw = source.read_bytes()
        source_sha = hashlib.sha256(raw).hexdigest()
        if source_sha != SOURCE_SHA or req["source_sha256"] != SOURCE_SHA:
            raise ValueError("SOURCE_VERSION_DENIED")
        start, end = item["span"]
        exact_bytes = raw[start:end]
        if exact_bytes.decode("utf-8") != item["byte_text"]:
            raise ValueError("SPAN_CONTENT_DENIED")
        citation = req["citation"]
        if citation != {"citation_id": "B0-OWNER-RULES/" + (
              "cache" if obligation == "cache_initial_mode" else "commander"),
                "source_sha256": SOURCE_SHA, "start_byte": start,
                "end_byte": end, "excerpt_sha256": hashlib.sha256(exact_bytes).hexdigest()}:
            raise ValueError("CITATION_DENIED")
        answer = req["answer"]
        if type(answer) is not str or answer.casefold().strip() not in item["answers"]:
            raise ValueError("NOT_ENTAILED")
        print(json.dumps({"accepted": True, "source_sha256": source_sha,
                          "obligation": obligation, "excerpt_sha256":
                          hashlib.sha256(exact_bytes).hexdigest(),
                          "independent_process": True, "signed_issuer": False}))
        return 0
    except Exception as exc:
        print(json.dumps({"accepted": False, "code": type(exc).__name__}))
        return 3

if __name__ == "__main__":
    sys.exit(main())
