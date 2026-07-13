# Governed tag taxonomy v0.1

This contract defines renderer-neutral discovery metadata. Canonical tags are lowercase,
dimensioned, unique, and stable. Aliases normalize to canonical tags before Source validation.

Tags never create canonical graph edges. Uncontrolled or AI-generated tags cannot enter
governed Source. A tag alias cannot shadow a canonical tag or point to another alias.
The normative schema is `schemas/tag-taxonomy-v0.1.schema.json`; the active registry is
`examples/tag-taxonomy.valid.json`.

Concept aliases are Source-owned lookup metadata. They do not create concepts or edges,
must normalize deterministically, and ambiguous ownership is a release-blocking error.
No renderer coordinates, colours, sizes, or Sigma-specific attributes belong in either contract.
