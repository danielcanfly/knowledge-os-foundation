// Independent Node stdlib-only implementation of deliberately narrow C1-subset.
// Not RFC8785/JCS, not Production ABI, not a signature or authorization.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const MAGIC = Buffer.from("M27-C1-LP-V1\0", "ascii");
const MAX_SAFE = Number.MAX_SAFE_INTEGER;
const REQUIRED = new Set([
  "schema_id", "tenant_id", "run_id", "task_id", "attempt",
  "issued_at", "expires_at", "consent_ref", "payload", "sidecars",
]);
const OPTIONAL = new Set(["memo"]);
const DOMAINS = {
  "m27.c1.envelope": "m27.envelope.binding.c1",
  "m27.c1.sidecar": "m27.sidecar.binding.c1",
};
const KEY = /^[a-z][a-z0-9_]*$/;
const TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const SHA = /^[0-9a-f]{64}$/;
const UNSIGNED_FIELDS = new Set([
  "amount_microunits", "price_microunits", "cost_microunits",
  "usage_microunits", "byte_count", "token_count",
]);
const RESERVED = new Set([
  "tenant_id", "run_id", "task_id", "attempt", "schema_id",
  "consent_ref", "auth_ref", "effective_auth", "signature", "signer_domain",
  "policy_generation", "revocation_generation", "allow_read", "allow_write",
  "approval_id", "privilege", "capability_id", "required_sidecars",
]);

class Denied extends Error {
  constructor(code) { super(code); this.code = code; }
}
function deny(code) { throw new Denied(code); }
function sha(buffer) { return createHash("sha256").update(buffer).digest("hex"); }
function bytes(hex) {
  if (typeof hex !== "string" || hex.length % 2 || !/^[0-9a-f]*$/.test(hex)) {
    deny("INVALID_HEX_BYTES");
  }
  return Buffer.from(hex, "hex");
}
function validatedString(value) {
  for (const char of value) {
    const code = char.codePointAt(0);
    if (code >= 0xd800 && code <= 0xdfff) deny("UNPAIRED_SURROGATE");
  }
  if (value.normalize("NFC") !== value) deny("NON_NFC_VALUE");
  return value;
}
function strictParse(data) {
  if (!Buffer.isBuffer(data) || data.length > 65536) deny("WIRE_SIZE_OR_TYPE_UNSUPPORTED");
  if (data.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf]))) {
    deny("UTF8_BOM_UNSUPPORTED");
  }
  let source;
  try { source = new TextDecoder("utf-8", { fatal: true }).decode(data); }
  catch { deny("INVALID_UTF8"); }
  let i = 0;
  function ws() { while (i < source.length && /[ \r\n\t]/.test(source[i])) i++; }
  function string() {
    const start = i;
    if (source[i++] !== '"') deny("INVALID_JSON");
    while (i < source.length) {
      if (source[i] === "\\") { i += 2; continue; }
      if (source[i] === '"') {
        i++;
        let decoded;
        try { decoded = JSON.parse(source.slice(start, i)); }
        catch { deny("INVALID_JSON"); }
        return validatedString(decoded);
      }
      i++;
    }
    deny("INVALID_JSON");
  }
  function number() {
    const rem = source.slice(i);
    const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(rem);
    if (!match) deny("INVALID_JSON");
    const lexeme = match[0];
    i += lexeme.length;
    if (lexeme.includes(".") || /[eE]/.test(lexeme)) deny("FLOAT_OR_EXPONENT_UNSUPPORTED");
    if (lexeme === "-0") deny("NEGATIVE_ZERO_UNSUPPORTED");
    const parsed = Number(lexeme);
    if (!Number.isSafeInteger(parsed) || parsed < 0 || parsed > MAX_SAFE) {
      deny("UNSAFE_OR_NEGATIVE_INTEGER");
    }
    return parsed;
  }
  function value(depth = 0, nested = false) {
    if (depth > 20) deny("DEPTH_UNSUPPORTED");
    ws();
    const c = source[i];
    if (c === '"') return string();
    if (c === "{") {
      i++; ws();
      const result = Object.create(null);
      const seen = new Set();
      if (source[i] === "}") { i++; return result; }
      while (true) {
        ws();
        if (source[i] !== '"') deny("INVALID_JSON");
        const key = string();
        if (!KEY.test(key)) deny("UNSUPPORTED_KEY_OR_NORMALIZATION");
        if (seen.has(key)) deny("DUPLICATE_JSON_KEY");
        if (nested && RESERVED.has(key)) deny("NESTED_AUTHORITY_SHADOW");
        seen.add(key); ws();
        if (source[i++] !== ":") deny("INVALID_JSON");
        result[key] = value(depth + 1, true);
        if (UNSIGNED_FIELDS.has(key) && (!Number.isSafeInteger(result[key])
            || typeof result[key] !== "number")) deny("UNSIGNED_FIELD_NOT_INT");
        ws();
        const sep = source[i++];
        if (sep === "}") break;
        if (sep !== ",") deny("INVALID_JSON");
      }
      return result;
    }
    if (c === "[") {
      i++; ws();
      const result = [];
      if (source[i] === "]") { i++; return result; }
      while (true) {
        result.push(value(depth + 1, nested));
        ws();
        const sep = source[i++];
        if (sep === "]") break;
        if (sep !== ",") deny("INVALID_JSON");
      }
      return result;
    }
    for (const [word, result] of [["true", true], ["false", false], ["null", null]]) {
      if (source.startsWith(word, i)) { i += word.length; return result; }
    }
    if (c === "-" || (c >= "0" && c <= "9")) return number();
    deny("INVALID_JSON");
  }
  const parsed = value();
  ws();
  if (i !== source.length) deny("INVALID_JSON");
  return parsed;
}
function date(input) {
  if (typeof input !== "string" || !TS.test(input)) deny("AMBIGUOUS_TIMESTAMP");
  const year = Number(input.slice(0, 4));
  if (year < 100) deny("INVALID_CALENDAR_TIMESTAMP");
  const date = new Date(input);
  if (Number.isNaN(date.getTime()) || date.toISOString() !== input) {
    deny("INVALID_CALENDAR_TIMESTAMP");
  }
  return date;
}
function parseC1(data) {
  const body = strictParse(data);
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    deny("BODY_NOT_OBJECT");
  }
  for (const k of REQUIRED) if (!Object.hasOwn(body, k)) deny("MISSING_REQUIRED_FIELD");
  for (const k of Object.keys(body)) {
    if (!REQUIRED.has(k) && !OPTIONAL.has(k)) deny("UNKNOWN_AUTHORITY_OR_BODY_FIELD");
  }
  if (!Object.hasOwn(DOMAINS, body.schema_id)) deny("UNRATIFIED_SCHEMA_UNSUPPORTED");
  for (const k of ["tenant_id", "run_id", "task_id"]) {
    if (typeof body[k] !== "string" || !body[k]) deny("SCOPE_OR_NULL_UNBOUND");
  }
  if (!Number.isSafeInteger(body.attempt) || typeof body.attempt !== "number") {
    deny("ATTEMPT_NOT_UNSIGNED_INT");
  }
  if (date(body.issued_at).getTime() >= date(body.expires_at).getTime()) {
    deny("TIMESTAMP_ORDER_INVALID");
  }
  if (body.consent_ref !== null && (typeof body.consent_ref !== "string" || !body.consent_ref)) {
    deny("CONSENT_REF_INVALID");
  }
  if (typeof body.payload !== "object" || body.payload === null || Array.isArray(body.payload)) {
    deny("PAYLOAD_NOT_OBJECT");
  }
  if (!Array.isArray(body.sidecars) || body.sidecars.length === 0) deny("REQUIRED_SIDECARS_MISSING");
  if (body.sidecars.some(s => typeof s !== "string" || !s)) deny("INVALID_SIDECAR_ID");
  if (new Set(body.sidecars).size !== body.sidecars.length) deny("DUPLICATE_SIDECAR_ID");
  if (Object.hasOwn(body, "memo") && body.memo !== null && typeof body.memo !== "string") {
    deny("MEMO_TYPE_INVALID");
  }
  return body;
}
function sortedValue(value) {
  if (Array.isArray(value)) return value.map(sortedValue);
  if (value !== null && typeof value === "object") {
    const out = Object.create(null);
    for (const k of Object.keys(value).sort()) out[k] = sortedValue(value[k]);
    return out;
  }
  return value;
}
function canonicalNew(data) {
  return Buffer.from(JSON.stringify(sortedValue(parseC1(data))), "utf8");
}
function legacyRef(raw) {
  // The digest is over the exact byte buffer; NEVER JSON.stringify legacy.
  if (!Buffer.isBuffer(raw)) deny("LEGACY_BYTES_REQUIRED");
  return { original: raw, sha: sha(raw), length: raw.length };
}
function frame(value) {
  if (value.length > 0xffffffff) deny("LENGTH_OVERFLOW");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(value.length);
  return Buffer.concat([length, value]);
}
function bindCandidate(v) {
  const raw = bytes(v.raw_hex);
  const legacyRaw = bytes(v.legacy_hex);
  const body = parseC1(raw);
  if (DOMAINS[body.schema_id] !== v.domain) deny("DOMAIN_SCHEMA_MISMATCH");
  if (body.tenant_id !== v.tenant_id || body.run_id !== v.run_id
      || body.task_id !== v.task_id || body.attempt !== v.attempt
      || !Number.isSafeInteger(v.attempt)) deny("IDENTITY_TUPLE_MISMATCH");
  const { sha: legacySha } = legacyRef(legacyRaw);
  if (v.expected_legacy_sha256 !== undefined
      && (!SHA.test(v.expected_legacy_sha256) || v.expected_legacy_sha256 !== legacySha)) {
    deny("LEGACY_DIGEST_MISMATCH");
  }
  const canonical = canonicalNew(raw);
  const values = [
    Buffer.from(v.domain, "ascii"), Buffer.from(body.schema_id, "ascii"),
    canonical, bytes(legacySha), Buffer.from(v.tenant_id, "utf8"),
    Buffer.from(v.run_id, "utf8"), Buffer.from(v.task_id, "utf8"),
    Buffer.from(String(v.attempt), "ascii"),
  ];
  const wire = Buffer.concat([MAGIC, ...values.map(frame)]);
  return {
    status: "CANDIDATE_DIGEST_UNRATIFIED",
    canonical_hex: canonical.toString("hex"),
    canonical_sha256: sha(canonical),
    legacy_raw_sha256: legacySha,
    binding_hex: wire.toString("hex"),
    binding_sha256: sha(wire),
  };
}
function calculate(v) {
  try { return { ok: true, ...bindCandidate(v) }; }
  catch (e) {
    if (e instanceof Denied) return { ok: false, error: e.code };
    throw e;
  }
}
function selfTest() {
  const source = {
    schema_id: "m27.c1.envelope",
    tenant_id: "tenant-a", run_id: "run-a", task_id: "task-a", attempt: 1,
    issued_at: "2026-10-10T00:00:00.000Z",
    expires_at: "2026-10-11T00:00:00.000Z",
    consent_ref: null, payload: { z: 1, a: "🌏", control: "\n\t" },
    sidecars: ["sidecar-a"],
  };
  const raw = Buffer.from(JSON.stringify(source));
  const base = { raw_hex: raw.toString("hex"), legacy_hex: Buffer.from('{"v":1 }').toString("hex"),
    domain: "m27.envelope.binding.c1", tenant_id: "tenant-a",
    run_id: "run-a", task_id: "task-a", attempt: 1 };
  const good = calculate(base);
  assert(good.ok && good.status === "CANDIDATE_DIGEST_UNRATIFIED");
  assert.equal(good.binding_sha256, "b865539b7ccf3490726c33688ae4db68dd83461594302ffbe2cdadc26346b339");
  const duplicate = { ...base, raw_hex: Buffer.from(
    raw.toString().replace('"tenant_id":"tenant-a"', '"tenant_id":"tenant-a","tenant_id":"tenant-b"')
  ).toString("hex") };
  assert.equal(calculate(duplicate).error, "DUPLICATE_JSON_KEY");
  const offset = { ...source, issued_at: "2026-10-10T08:00:00+08:00" };
  assert.equal(calculate({ ...base, raw_hex: Buffer.from(JSON.stringify(offset)).toString("hex") }).error,
    "AMBIGUOUS_TIMESTAMP");
  const crossRun = calculate({ ...base, run_id: "run-b" });
  assert.equal(crossRun.error, "IDENTITY_TUPLE_MISMATCH");
  const swapped = calculate({ ...base, domain: "m27.sidecar.binding.c1" });
  assert.equal(swapped.error, "DOMAIN_SCHEMA_MISMATCH");
  console.log(JSON.stringify({ selftest: "PASS", assertions: 6,
    golden_hex: good.canonical_hex, golden_binding_sha256: good.binding_sha256 }));
}

if (process.argv[2] === "--selftest") {
  selfTest();
} else if (process.argv[2] === "--batch") {
  // CLI transport JSON is test harness-only and never counted as authority.
  const input = JSON.parse(readFileSync(0, "utf8"));
  if (!Array.isArray(input.vectors)) deny("INVALID_BATCH");
  console.log(JSON.stringify(input.vectors.map(calculate)));
} else {
  console.error("usage: node m27_wire_oracle.mjs --selftest|--batch");
  process.exitCode = 2;
}
