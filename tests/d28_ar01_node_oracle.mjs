// D28 independent Node SHA256/canonical byte reader fixture; no trust issuer.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const vectors = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const SHA = (buf) => createHash('sha256').update(buf).digest('hex');
const canonical = (v) => {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v !== null && typeof v === 'object') {
    return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  }
  return JSON.stringify(v);
};
let verified = 0;
for (const [name, entry] of Object.entries(vectors)) {
  const bytes = Buffer.from(entry.wire_hex, 'hex');
  const text = bytes.toString('utf8');
  const parsed = JSON.parse(text);
  if (canonical(parsed) !== text) throw Error(name + ': noncanonical');
  if (SHA(bytes) !== entry.wire_sha256) throw Error(name + ': wire sha mismatch');
  const digest = parsed.envelope_digest;
  const { envelope_digest, ...body } = parsed;
  const raw = Buffer.from(canonical(body));
  const n = Buffer.alloc(4);
  n.writeUInt32BE(raw.length);
  const signed = Buffer.concat([Buffer.from('M27-D28-AR01-ABI-CANDIDATE\0'), n, raw]);
  if (SHA(signed) !== digest || digest !== entry.envelope_digest) {
    throw Error(name + ': domain length frame/hash mismatch');
  }
  if (name === 'legacy') {
    const old = Buffer.from('{ "event_id":"evt-1",  "occurred_at":"2026-10-09T05:00:00Z", "legacy":null }');
    if (SHA(old) !== parsed.legacy_ref.raw_sha256 ||
        old.length !== parsed.legacy_ref.raw_byte_length) {
      throw Error(name + ': historical raw bytes changed');
    }
  } else if (parsed.legacy_ref !== undefined) {
    throw Error(name + ': false legacy binding');
  }
  verified++;
}
process.stdout.write(JSON.stringify({verified, errors: 0}) + '\n');
