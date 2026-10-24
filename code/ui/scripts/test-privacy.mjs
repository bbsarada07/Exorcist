// npm run test:privacy — fails (exit 1) if the UI's static data or built bundle could leak personal data.
// Scans code/ui/public/data (and dist/ if present) for: unmasked emails, phone numbers, 64-char hex hashes,
// subject names from dataset/user_identities.csv (when the dataset is available), raw request texts, and any
// field that is not a derived engine output.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const UI = join(here, "..");
const DATA = join(UI, "public", "data");
const DATASET = join(UI, "..", "..", "dataset");

const files = (dir) => existsSync(dir) ? readdirSync(dir, { recursive: true }).map((f) => join(dir, String(f)))
  .filter((p) => statSync(p).isFile() && /\.(json|js|html|css)$/.test(p)) : [];
// our data export, our own source, and the data copied into a build; third-party bundles (license headers,
// CSS unicode-ranges) are out of scope and produce false positives
const targets = [...files(DATA), ...files(join(UI, "src")).concat(
  readdirSafe(join(UI, "src")).filter((p) => /\.(ts|tsx)$/.test(p))), ...files(join(UI, "dist", "data"))];
function readdirSafe(dir) {
  return existsSync(dir) ? readdirSync(dir, { recursive: true }).map((f) => join(dir, String(f))).filter((p) => statSync(p).isFile()) : [];
}
const corpus = targets.map((p) => [p, readFileSync(p, "utf8")]);

const csvColumn = (file, col) => {
  const [head, ...rows] = readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean);
  const i = head.split(",").indexOf(col);
  return rows.map((r) => r.split(",")[i]).filter(Boolean);
};

const checks = {
  // an email whose local part or domain is not masked with bullets
  unmasked_email: /[A-Za-z0-9._%+-]{2,}@(?!••)[A-Za-z0-9-]+\.[A-Za-z]{2,}/g,
  phone_number: /(?<![U\w])\+\d{1,3}[ \-()]*\d[\d \-()]{6,}\d/g,   // not CSS unicode-range (U+0490-0491)
  hex64_hash: /\b[0-9a-f]{64}\b/g,
};
const counts = Object.fromEntries(Object.keys(checks).map((k) => [k, 0]));
const examples = {};
for (const [p, text] of corpus) {
  for (const [k, re] of Object.entries(checks)) {
    const m = text.match(re) ?? [];
    counts[k] += m.length;
    if (m.length && !examples[k]) examples[k] = `${p.slice(UI.length + 1)}: ${m[0]}`;
  }
}

// person names + raw request texts from the dataset (skipped, with a note, when dataset/ is not present e.g. in code.zip)
let datasetChecked = false;
if (existsSync(join(DATASET, "user_identities.csv"))) {
  datasetChecked = true;
  const names = [...new Set(csvColumn(join(DATASET, "user_identities.csv"), "name"))].filter((n) => n.includes(" "));
  counts.dataset_person_name = 0;
  for (const [p, text] of corpus) for (const n of names) if (text.includes(n)) {
    counts.dataset_person_name++; examples.dataset_person_name ??= `${p.slice(UI.length + 1)}: ${n}`;
  }
  const requests = readFileSync(join(DATASET, "deletion_requests.csv"), "utf8");
  const texts = [...requests.matchAll(/,(?:"([^"]{40,})"|([^,\n"]{40,}))\r?$/gm)].map((m) => (m[1] ?? m[2]).slice(0, 60));
  counts.raw_request_text = 0;
  for (const [p, text] of corpus) for (const t of texts) if (text.includes(t)) {
    counts.raw_request_text++; examples.raw_request_text ??= `${p.slice(UI.length + 1)}: "${t.slice(0, 40)}…"`;
  }
}

// structural check: the per-case export may only carry derived fields
const ALLOWED = new Set(["id", "status", "reported", "requested_at", "reported_at", "audit_at", "email", "user_id",
  "identity_match", "intent", "confidence", "confidence_reasons", "review", "verdict", "failure_modes", "steps", "why",
  "assessed", "lineage", "risk", "conflicts"]);
counts.non_derived_field = 0;
const det = join(DATA, "details.json");
if (existsSync(det)) for (const c of Object.values(JSON.parse(readFileSync(det, "utf8"))))
  for (const k of Object.keys(c)) if (!ALLOWED.has(k)) { counts.non_derived_field++; examples.non_derived_field ??= k; }

const size = files(DATA).reduce((s, p) => s + statSync(p).size, 0);
console.log(`scanned ${corpus.length} files (public/data, src${existsSync(join(UI, "dist", "data")) ? ", dist/data" : ""}); public/data size ${(size / 1024).toFixed(0)} KB`);
for (const [k, v] of Object.entries(counts)) console.log(`  ${k.padEnd(20)} ${v === 0 ? "0 found" : `${v} FOUND  e.g. ${examples[k]}`}`);
if (!datasetChecked) console.log("  (dataset/ not present: name and request-text checks skipped)");
const bad = Object.values(counts).some((v) => v > 0);
console.log(bad ? "PRIVACY CHECK FAILED" : "privacy check passed");
process.exit(bad ? 1 : 0);
