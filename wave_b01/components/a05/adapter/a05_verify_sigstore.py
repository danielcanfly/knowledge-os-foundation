"""A05 fresh read-only OIDC Sigstore proof of the 11 exact signed source docs."""
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path
from a05_retrieval import ContextIndex
H=Path(__file__).resolve().parent
W=H.parent
BASE=W.parent.parent
S=BASE/"MG22_SIGNED_FIRST_PARTY_SOURCE_APP_20261014"
ARCHIVE=S/"package/mg22-owner-firstparty-source-and-app-v1.tar.gz"
BUNDLE=S/"evidence/mg22-owner-firstparty-source.sigstore.json"
COSIGN=BASE/"MG17_NONPROD_GITHUB_PROVENANCE_20261013/tools/cosign-darwin-arm64"
IDENTITY="https://github.com/danielcanfly/m27-nonprod-provenance-20261013/.github/workflows/nonprod-owner-source-attestation.yml@refs/heads/main"
def sha(b):return hashlib.sha256(b).hexdigest()
checks={}
run=subprocess.run([str(COSIGN),"verify-blob",str(ARCHIVE),"--bundle",str(BUNDLE),
                    "--certificate-identity="+IDENTITY,
                    "--certificate-oidc-issuer=https://token.actions.githubusercontent.com"],
                   capture_output=True,text=True,timeout=60)
(W/"evidence/raw/a05_sigstore.stdout.log").write_text(run.stdout)
(W/"evidence/raw/a05_sigstore.stderr.log").write_text(run.stderr)
checks["ACTUAL_PUBLIC_OIDC_SIGSTORE_VERIFIED"]=run.returncode==0 and "Verified OK" in run.stdout+run.stderr
if not checks["ACTUAL_PUBLIC_OIDC_SIGSTORE_VERIFIED"]:
    raise RuntimeError("SIGNED_SOURCE_CHAIN_UNVERIFIED")
idx=ContextIndex()
with tarfile.open(ARCHIVE,"r:gz") as tf:
    assert all(x.isfile() for x in tf.getmembers())
    docs={x.name:tf.extractfile(x).read() for x in tf.getmembers()}
checks["EXACT_14_SIGNED_SOURCE_APP_MEMBER_COUNT"]=len(docs)==14
checks["EXACT_SIGNED_FIRST_PARTY_CORPUS_MANIFEST"]=docs["corpus/corpus.json"]==(idx.root/"corpus.json").read_bytes()
checks["EXACT_SIGNED_11_DOCUMENT_BYTES"]=all(docs["corpus/"+name]==(idx.root/name).read_bytes() for name in idx.docs)
checks["EXACT_SIGNED_21_SOURCE_SPANS"]=all(
    sha(docs["corpus/"+sec["source_filename"]][sec["byte_start"]:sec["byte_end"]])==sec["quote_sha256"]
    and docs["corpus/"+sec["source_filename"]][sec["byte_start"]:sec["byte_end"]].decode()==sec["quote"]
    for sec in idx.sections)
checks["SIGNED_PACKAGE_SHA_MATCH_PREVIOUS"]=sha(ARCHIVE.read_bytes())=="d7eef0b1948b7fc215f37f0015acee52bc92973c2029cb5577320b5c08469230"
checks["NEW_RELEASE_IS_NOT_CI_SIGNED"]=idx.release["source_release_ci_signed"] is False
checks["NO_PROTECTED_EVAL_DATA"]=not idx.corpus["original523_included"] and not idx.corpus["blind200_included"]
result={"schema":"m27.a05.source_lineage_real_oidc_sigstore.v1","checks":checks,
        "passed":sum(checks.values()),"total":len(checks),
        "all_pass":all(checks.values()),"cosign_exit":run.returncode,
        "signed_original_source_archive_sha256":sha(ARCHIVE.read_bytes()),
        "signed_document_count":len(idx.docs),"signed_passage_count":len(idx.sections),
        "new_transformed_a05_release_ci_signed":False,
        "new_transformed_a05_native_release_ci_signed":False}
(W/"evidence/A05_SIGNED_SOURCE_PROVENANCE.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k!="checks"}))
raise SystemExit(0 if result["all_pass"] else 2)
