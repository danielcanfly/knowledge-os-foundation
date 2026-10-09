# AR03A offline context mock receipts
EXPERIMENTAL_NO_LIVE_PROVIDER. All tests are mocked fixtures, not integrated authorization.
No real provider, policy signer, identity, consent, native Q&A, action, tool or network access.
GrantFixture.externally_authenticated is an untrusted caller assertion and cannot be used for production admission. The demo uses this flag ONLY in offline tests. Production must fail closed without independent authenticated grant.
Candidate payload and taint remain inert data; no instructions executed, no content published, no citations emitted. Native evidence pin function only compares caller-provided identity/digest under a mock verified flag. Genuine byte-level authority must be independently verified.
X01-X09 remain OPEN; no AR03 live release or signoff.
