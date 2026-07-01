# Repository and Storage Map

## Governance repositories

- `knowledge-docs-system`: reusable document templates, authoring rules, and document linting.
- `knowledge-os-foundation`: normative architecture, executable contracts, schemas, fixtures, and reference implementation.

## Core system boundaries

- `knowledge-source`: source snapshots and reviewed OKF authoring workspace.
- `knowledge-builder`: deterministic compiler that validates and emits runtime artifacts.
- Cloudflare R2 `knowledge-store`: immutable `releases/` plus mutable `channels/` pointers.
- Query consumer: loads one complete release, performs Wiki-first retrieval, and never reads a half-published build.

New core repositories should not invent their own schema. They consume versioned contracts from this repository.
