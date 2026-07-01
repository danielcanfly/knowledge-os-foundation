# Release Lifecycle

A release is created in this order:

1. validate the OKF bundle and provenance;
2. compile graph, lexical index, provenance aggregate, and build report;
3. produce a deterministic bundle archive;
4. calculate hashes and write `manifest.json`;
5. upload the immutable `releases/<release-id>/` prefix;
6. verify all uploaded objects against the manifest;
7. update `channels/staging.json` or `channels/production.json` last.

The channel pointer is the only mutable object. Rollback changes the pointer to a previously verified release. Runtime instances pin a release for the duration of each query.
