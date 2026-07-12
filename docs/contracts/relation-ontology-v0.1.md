# Knowledge OS Relation Ontology v0.1

- Contract ID: `KOS-REL-001`
- Ontology ID: `daniel-knowledge-os/relation-ontology`
- Version: `0.1.0`
- Status: Normative Draft
- Canonical fixture: `examples/relation-ontology.valid.json`
- Schema: `schemas/relation-ontology-v0.1.schema.json`

## Scope

This contract defines renderer-neutral semantic relation types for reviewed Knowledge OS Source. It does not define graph layout, colour, coordinates, Graphology attributes, Sigma reducers, vector similarity, or query-time inferred edges.

Typed relations are reviewed facts or reviewed structural assertions. Markdown links remain the readable expression of knowledge, but anchor text alone cannot establish a typed relation.

## Ownership

Foundation owns the base schema and semantics. A Source repository pins an exact Foundation commit and ontology version, then declares any governed domain extension allowed by a future Foundation extension contract. Engine validates and compiles; it does not invent relation meaning.

## Direction model

Every type declares exactly one of:

- `directed: true, symmetric: false`; or
- `directed: false, symmetric: true`.

Every directed type has a separately declared reciprocal inverse. Every symmetric type is self-inverse. A Source declaration uses the canonical forward type; consumers may traverse the explicit inverse without requiring a duplicate editable Source statement.

## Initial ontology

| Primary type | Inverse | Meaning |
|---|---|---|
| `is_a` | `has_subtype` | taxonomy |
| `part_of` | `has_part` | composition |
| `uses` | `used_by` | dependency or technique |
| `produces` | `produced_by` | explicit output |
| `requires` | `required_by` | stated precondition |
| `implements` | `implemented_by` | implementation |
| `supports` | `supported_by` | explicit support |
| `contrasts_with` | self | reviewed comparison |
| `complements` | self | complementary capabilities |
| `alternative_to` | self | comparable alternatives |
| `supersedes` | `superseded_by` | explicit replacement |
| `related_to` | self | last-resort reviewed relation |

The inverse declarations are first-class ontology entries, producing 20 declared types. `related_to` is permitted only when no narrower approved type applies.

## Provenance expectations

- `required_factual`: claim-level evidence is mandatory.
- `reviewed_structural`: an approved structural basis is mandatory.
- `required_or_reviewed_structural`: either claim evidence or approved structural basis is mandatory.

Confidence is advisory metadata and never replaces review or evidence.

## Source declaration shape

A release-conformant Source may declare:

```yaml
x-kos-relations:
  - target: concepts/react
    type: contrasts_with
    direction: undirected
    confidence: 0.95
    qualifiers:
      context: agent decision strategy
    provenance:
      record: provenance/agent-planning-strategies.json
      claim_id: claim_plan_react_difference
    review:
      status: approved
      review_id: review_relation_example
```

Rules:

1. `target` is an immutable concept path identity, not a title or alias.
2. Type and direction match the pinned ontology.
3. Unknown target, type, or qualifier fails closed.
4. Self-loops are forbidden in v0.1.
5. A relation is no less restrictive than both endpoints and its evidence.
6. Missing or unapproved review fails closed.
7. Required evidence must resolve to the declared provenance record and claim.
8. Symmetric duplicates normalize endpoint order and are rejected as duplicate editable truth.
9. AI extraction may propose a candidate but cannot approve or write canonical Source.
10. Shared tags, lexical similarity, and vector similarity never create canonical relations.

## Compatibility

Generic Markdown `links_to` and typed semantic relations remain distinct. Existing v1-style graph consumers must not reinterpret `links_to` as a factual typed edge. Graph v2 work occurs in M18.4, not in this contract milestone.

## Validation

```bash
python scripts/validate_relation_ontology.py
pytest -q
```

Validation fails on schema drift, renderer-specific fields, duplicate types, missing or non-reciprocal inverses, invalid direction/symmetry, or an invalid fallback.
