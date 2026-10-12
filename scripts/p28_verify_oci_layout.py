#!/usr/bin/env python3
"""Validate actual local unsigned OCI tar (blob digests, manifest/config/entrypoint)."""

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

HEAD = "8604752934fb43a3441055d33c01940028cc5938"
TREE = "123578f9e1059d1b554fc3fdc011bdc171033afd"
CMD = ["uvicorn", "knowledge_engine.m26_production_api:app", "--host", "0.0.0.0", "--port", "8080"]


def hash_stream(handle):
    h = hashlib.sha256()
    n = 0
    while True:
        data = handle.read(1024 * 1024)
        if not data:
            break
        h.update(data)
        n += len(data)
    return h.hexdigest(), n


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--oci", required=True, type=Path)
    a.add_argument("--image", required=True)
    a.add_argument("--manifest", required=True, type=Path)
    a.add_argument("--receipt", required=True, type=Path)
    v = a.parse_args()
    expected_source = json.loads(v.manifest.read_text())
    with tarfile.open(v.oci, "r") as tf:

        def read(name):
            handle = tf.extractfile(name)
            if handle is None:
                raise ValueError("missing OCI member: " + name)
            return handle.read()

        if json.loads(read("oci-layout")) != {"imageLayoutVersion": "1.0.0"}:
            raise ValueError("invalid OCI-layout marker")
        index = json.loads(read("index.json"))
        if index.get("mediaType") != "application/vnd.oci.image.index.v1+json":
            raise ValueError("invalid index media type")
        for descriptor in index["manifests"]:
            digest = descriptor["digest"]
            if not digest.startswith("sha256:"):
                raise ValueError("not SHA256")
            raw = read("blobs/sha256/" + digest[7:])
            if hashlib.sha256(raw).hexdigest() != digest[7:]:
                raise ValueError("OCI manifest digest mismatch")
        image_descriptors = [
            x
            for x in index["manifests"]
            if x.get("platform", {}).get("architecture") == "arm64"
            and x.get("platform", {}).get("os") == "linux"
        ]
        if len(image_descriptors) != 1:
            raise ValueError("expected exactly one linux/arm64 OCI image")
        d = image_descriptors[0]
        manifest = json.loads(read("blobs/sha256/" + d["digest"][7:]))
        config_digest = manifest["config"]["digest"]
        config = json.loads(read("blobs/sha256/" + config_digest[7:]))
        labels = config["config"]["Labels"]
        if (
            labels.get("org.opencontainers.image.revision") != HEAD
            or labels.get("org.opencontainers.image.source_tree") != TREE
        ):
            raise ValueError("OCI source lineage wrong")
        if labels.get("io.knowledge_engine.signed") != "false":
            raise ValueError("invalid signature claim")
        if config["config"]["Cmd"] != CMD:
            raise ValueError("wrong canonical M26 app command")
        verified = []
        for m in tf.getmembers():
            if not m.isfile() or not m.name.startswith("blobs/sha256/"):
                continue
            h, size = hash_stream(tf.extractfile(m))
            if h != m.name.removeprefix("blobs/sha256/"):
                raise ValueError("OCI blob mismatch " + m.name)
            verified.append({"digest": "sha256:" + h, "bytes": size})
        if len(manifest["layers"]) != len(config["rootfs"]["diff_ids"]):
            raise ValueError("layer/rootfs count mismatch")
    docker = json.loads(subprocess.check_output(["docker", "image", "inspect", v.image]))[0]
    # Docker Desktop containerd store reports the local IMAGE INDEX digest as .Id,
    # not the OCI *CONFIG* digest. Verify equal rootfs diff IDs, labels and Cmd.
    if docker["RootFS"]["Layers"] != config["rootfs"]["diff_ids"]:
        raise ValueError("running local image rootfs differs from OCI config")
    if docker["Config"]["Cmd"] != config["config"]["Cmd"]:
        raise ValueError("running local image command differs")
    if docker["Config"]["Labels"] != labels:
        raise ValueError("running local image labels differ")
    with v.oci.open("rb") as f:
        tar_sha, tar_size = hash_stream(f)
    receipt = {
        "schema": "P28_REAL_LOCAL_OCI_MANIFEST_CONFIG_VERIFY_V1",
        "oci_archive": str(v.oci),
        "oci_tar_sha256": tar_sha,
        "oci_tar_bytes": tar_size,
        "index": index,
        "linux_arm64_manifest_digest": d["digest"],
        "config_digest": config_digest,
        "local_docker_index_digest": docker["Id"],
        "config_matches_local_rootfs_and_command": True,
        "entrypoint": config["config"].get("Entrypoint"),
        "cmd": config["config"]["Cmd"],
        "environment": config["config"]["Env"],
        "working_dir": config["config"]["WorkingDir"],
        "user": config["config"]["User"],
        "nonprod_labels": labels,
        "layer_count": len(manifest["layers"]),
        "verified_oci_blob_count": len(verified),
        "verified_blob_total_bytes": sum(x["bytes"] for x in verified),
        "git_source_head": HEAD,
        "git_source_tree": TREE,
        "source_copy_file_count": expected_source["scoped_source_file_count"],
        "source_copy_manifest_sha256": expected_source["scoped_manifest_sha256"],
        "independent_ci_signature": False,
        "nonprod_registry_push": False,
        "real_external_provider_trial": False,
        "release_grade": False,
        "claim": "actual OCI layout exported from local nonprod build; unsigned",
    }
    v.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "linux_arm64_manifest_digest",
                    "config_digest",
                    "verified_oci_blob_count",
                    "oci_tar_sha256",
                    "oci_tar_bytes",
                    "source_copy_file_count",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print("P28 OCI VERIFICATION FAIL: " + str(exc), file=sys.stderr)
        sys.exit(28)
