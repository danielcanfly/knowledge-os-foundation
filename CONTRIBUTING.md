# Contributing

## Contract changes

Any change to a normative contract, JSON Schema, release layout, ACL rule, or runtime wire format must:

1. update the relevant contract document;
2. add or update positive and negative fixtures;
3. pass `make ci`;
4. document compatibility and migration impact;
5. use an ADR when the change alters a cross-repository boundary.

## Commit prefixes

- `docs:` documentation only
- `contract:` normative contract or schema
- `test:` fixtures and validation coverage
- `ref:` reference implementation
- `ci:` automation

Generated runtime artifacts must never be edited by hand.
