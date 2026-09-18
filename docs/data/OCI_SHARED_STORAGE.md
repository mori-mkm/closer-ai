# OCI Shared Data Foundation

Owner: Matheus. Not a data platform — the smallest shared foundation for Matheus, Gabriel, and
Otávio to work from reproducible snapshots of real Calls/CRM data without ever putting real
data in Git.

**Status: provisioned and smoke-tested with 100% synthetic data (2026-09-18)** — compartment,
bucket, IAM groups, and budget all exist and match this design (see "IAM" and "Exact console/
CLI setup steps" below for exactly what's done vs. still pending). No real Agro/Empreende/CRM
data has been uploaded — that still requires authorization + storage decision + access review
(see `docs/context/HUMAN_DECISIONS.md`) to all be separately confirmed first.

```
Partners / Sources
    ↓
OCI Object Storage (private, NoPublicAccess)
    ↓
Raw snapshots + manifests
    ↓
local sync → Real Call Validation Kit (docs/data/REAL_CALL_VALIDATION_KIT.md)
    ↓
Canonical / curated datasets
```

## Purpose

Today, "shared data" means someone manually sends a file to someone else. That doesn't scale
to three people validating against the same snapshots and doesn't produce a reproducible
record of what was received, when, from whom, under what authorization. OCI Object Storage
fixes exactly that gap — nothing more.

## Architecture

One private bucket, one compartment, three IAM groups, the manifest schema the Real Call
Validation Kit already defined (unchanged in this branch — only `storage_location`'s comment
was reworded to document it as the OCI URI), and a documented CLI-based sync workflow. No
database, no orchestration, no SDK wrapper — see "What NOT to build yet" for why each of those
is deferred, not forgotten.

## Bucket decision: ONE

```
ai-closer-private/
├── raw/
│   ├── agro/<dataset_id>/
│   ├── empreende/<dataset_id>/
│   └── crm/<dataset_id>/
├── curated/
│   └── annotation/<dataset_id>/        (only prefix created now — see below)
└── manifests/
    ├── agro/<dataset_id>.yaml
    ├── empreende/<dataset_id>.yaml
    └── crm/<dataset_id>.yaml
```

`curated/canonical/` and `curated/matching/` are documented as **reserved, not created** — no
code produces that output yet (same reasoning as `src/closer_ai/analytics/` staying an empty
package: don't create a destination before something writes to it).

`<dataset_id>` is the manifest's own `dataset_id` field reused directly as the folder name
(e.g. `agro-sample-2026-09-18`) — one naming source, not a parallel snapshot-naming scheme.
Never a customer/lead name, email, or phone in any object key.

### Option A (one bucket, chosen) vs. Option B (two buckets)

| | One bucket + prefixes | Two buckets |
|---|---|---|
| Simplicity | One thing to create/monitor/quota-track | Two of everything |
| IAM | **Viable**: OCI IAM policies support object-name prefix conditions (`target.object.name = 'raw/crm/*'` combined with `target.bucket.name`) per [Oracle's Advanced Policy Features docs](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policyadvancedfeatures.htm), checked 2026-09-18 — the feature itself is real, but exact statement syntax should still be validated against current docs at implementation time (see policy examples below), not copy-pasted as guaranteed-correct | Same separation, no simpler |
| Accidental cross-writes | Prevented by IAM policy, not by bucket boundary — same guarantee | Prevented by bucket boundary |
| Lifecycle | Lifecycle rules can also be scoped by object-name prefix within one bucket | Per-bucket rules, more surface |
| Reproducibility | One manifest namespace | Split across two |
| Cost | Free Tier quota is per-tenancy, not per-bucket — no difference | No difference |

The only real argument for two buckets (simpler policy language) doesn't hold once prefix-
scoped IAM policies are confirmed viable, and one bucket is strictly less to operate for three
people and a handful of snapshots. **Chosen: Option A.**

## Access model (least privilege)

| Person | Access |
|---|---|
| **Matheus** | Full read/write across the whole bucket, bucket/lifecycle/PAR management. Only person who promotes `raw/` → `curated/annotation/`. |
| **Gabriel** | Read/write scoped to `raw/crm/*` and `manifests/crm/*` only. **No access to `raw/agro/*` or `raw/empreende/*`** — he contributes CRM snapshots, he doesn't need to see raw Calls (task explicit instruction). |
| **Otávio** | Read-only, scoped to `curated/annotation/*` only. He consumes calls already promoted to "ready for annotation" — never the raw bucket, never CRM data. |

## IAM

**Provisioned** (verified 2026-09-18 via `oci iam compartment get`/`group list`/`policy list`,
read-only checks, no credentials inspected). One compartment (`ai-closer`, under tenancy root)
and three groups:

```
ai-closer-admins    (Matheus)  — full administration of AI Closer cloud data resources
ai-closer-business   (Gabriel) — restricted access to CRM and business-review data
ai-closer-ai         (Otávio)  — restricted read access to approved annotation datasets
```

Only one policy exists so far — `ai-closer-object-storage-access`:

```
Allow group ai-closer-admins to manage object-family in compartment ai-closer
```

**Known gap, confirmed by the operational smoke test**: `ai-closer-business` and `ai-closer-ai`
have **no policy statement yet** — both groups exist but currently grant zero access (fails
closed, not a security problem, but incomplete relative to the design below). Adding their
scoped policies is a deliberate follow-up requiring explicit sign-off, not done automatically
by this smoke test. Illustrative statements to add when ready — validate exact syntax against
current OCI policy docs at that time:

```
Allow group ai-closer-business to manage objects in compartment ai-closer
  where all {target.bucket.name = 'ai-closer-private', target.object.name = 'raw/crm/*'}
Allow group ai-closer-business to manage objects in compartment ai-closer
  where all {target.bucket.name = 'ai-closer-private', target.object.name = 'manifests/crm/*'}

Allow group ai-closer-ai to read objects in compartment ai-closer
  where all {target.bucket.name = 'ai-closer-private', target.object.name = 'curated/annotation/*'}
```

Three groups, not the ten+ a general-purpose data platform would have. No dynamic groups, no
resource principals — nothing here runs as an automated service yet.

## Security

- **NoPublicAccess** on the bucket — non-negotiable. Verified twice: via `oci os bucket get`
  metadata (`public-access-type: NoPublicAccess`) and empirically, an unauthenticated `curl`
  against both an object URL and the bucket listing URL both returned 404 (2026-09-18).
- **Encryption at rest**: AES-256, on by default for every OCI Object Storage bucket — no
  configuration needed, confirmed against current OCI docs.
- **Versioning**: **enabled** on the bucket (verified). Protects against an accidental
  overwrite — proven directly: a synthetic object was deliberately overwritten, its original
  content recovered byte-for-byte via its version-id, and restored as current, then the test's
  extra version was purged, consistent with the Real Call Validation Kit's raw-immutability
  principle below.
- **Object overwrite behavior**: with versioning on, an overwrite creates a new version rather
  than destroying data; old versions still cost storage, so pair with a lifecycle rule (below).
- **Lifecycle**: a simple rule to expire noncurrent object versions after a short window (e.g.
  30-60 days) keeps accidental-reupload cost bounded without manual cleanup — **not yet
  configured**, a real follow-up (see "Exact console/CLI setup steps"). No tiering to Infrequent
  Access/Archive yet — the working set is small and needs to stay quickly accessible during
  active MVP validation.
- **Audit**: OCI Audit logging is on by default at the tenancy level for API calls (bucket/
  object operations included) — no extra setup required, just don't disable it.

## Raw immutability principle (reused from the Real Call Validation Kit)

```
Source → snapshot → RAW (never silently edited)
RAW → processing → CURATED
```

A new export from a partner is a new `dataset_id`/snapshot, never an edit to an existing one.
This is already the Real Call Validation Kit's own principle (see its manifest's
`ingestion_status`/`validation_status` fields) — OCI just gives it a durable, shared home
instead of a laptop.

## Partner upload (Pre-Authenticated Request)

For partner-facing upload of new samples, a scoped, time-limited PAR is the right tool —
**not created in this task**, no partner data flows during this branch. Recommended shape when
actually needed:

- Access type: **write-only** (`ObjectWrite`), never read, never read-write.
- Scoped to a single prefix (`raw/agro/<new-dataset_id>/`), never the whole bucket.
- Listing **disabled** (default behavior — OCI PARs can't list objects unless explicitly
  enabled; leave that off).
- Short expiration — days, not months. OCI requires an explicit expiration date (no default,
  no unlimited option).
- Revoke (delete) the PAR as soon as the upload is confirmed received, don't wait for natural
  expiration.
- **A PAR URL is a bearer credential**: whoever has the URL has exactly the access it grants,
  confirmed by OCI's own docs — never in Git, Slack history, or any public channel. Note: OCI
  PARs cannot be used to delete objects/buckets even by design, one structural safety net, not
  a substitute for careful URL handling.

## Local workflow (Real Call Validation Kit integration)

```
OCI raw snapshot (oci://ai-closer-private/raw/agro/<dataset_id>/)
    ↓  oci os object bulk-download  (OCI CLI, not a new SDK wrapper — see below)
data/raw/agro/  (local, gitignored, ephemeral — reproducible from OCI any time)
    ↓
closer_ai.ingestion.profiling.profile_directory()   (already exists, unchanged)
    ↓
closer_ai.ingestion.profiling.summarize_capacity()   (new — see "Capacity discovery")
    ↓
docs/data/REAL_CALL_VALIDATION_KIT.md Execution Runbook, step 6 onward
```

The structural profiler is not modified for OCI — it already operates on local files and
knows nothing about where they came from, which is exactly right (see "Domain coupling"
below). Its `size_bytes` field, already privacy-safe, is now also the input to capacity
discovery.

## Capacity discovery

Reuses `profile_directory()` — no new upload/inspection step needed. New:
`closer_ai.ingestion.profiling.summarize_capacity(profiles) -> dict[str, int]`, total bytes
per file format across a batch (`{"json": ..., "vtt": ..., "unsupported:.mp3": ...}`). This is
the first *real* number to base the "upload everything vs. transcript+metadata first" decision
on — never an estimate stated as fact before real files exist.

## MVP storage policy (proposal, needs human sign-off before real data flows)

- Transcripts, meeting metadata, CRM exports, manifests → cloud, always.
- Audio/video → **only when a validation need or confirmed capacity headroom justifies it**,
  not by default. `summarize_capacity()`'s `unsupported:.mp3`/`.mp4`/etc. buckets are exactly
  the numbers this decision needs.

## OCI Free Tier — current official limits

Source: [Oracle Cloud docs, "Always Free Resources"](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), fetched 2026-09-18.

- **Storage**: on a paid/trial account, 10 GB Standard + 10 GB Infrequent Access + 10 GB
  Archive (30 GB total, separately metered). Once a Free Trial expires and the account becomes
  **Always-Free-only**, this collapses to **20 GB combined** across all three tiers — and
  **exceeding 20 GB at that point triggers automatic deletion of objects**, per Oracle's own
  docs. This is the single most important number to track over time, not a one-time check.
- **API requests**: 50,000 Object Storage requests/month (Always Free).
- **Outbound data transfer**: 10 TB/month (applies to all Always Free accounts).
- **Region**: Always Free resources live in the tenancy's home region; no separate
  Object-Storage-specific region restriction found in the docs beyond that.

For this project's expected volume (108 + 35 calls, transcripts + metadata, no audio/video by
default) — plausibly well under 10 GB, but this is a plausibility statement, not a measured
fact. `summarize_capacity()` (above) is how that gets confirmed once real files exist, not
assumed here.

## Cost guardrails

- Create a Budget (Billing → Cost Management → Budgets) at a low threshold — **$1** is a
  reasonable ping-immediately-on-any-charge threshold, per common OCI operator practice for
  small tenancies.
- Two alert rules: 50% ($0.50) as an early warning, 100% ($1.00) as critical.
- Treat alerts as a backstop, not a guarantee — Oracle's own community guidance notes alerts
  aren't instantaneous; the real guardrail is staying inside Always Free limits in the first
  place (20 GB storage ceiling above).
- No paid resources are provisioned automatically by anything in this branch or its runbook.

## Domain coupling

**NONE, by design.** Nothing under `src/closer_ai/normalization/`, `domain/`, or `ai/` gains an
`oci_bucket`/`oracle_namespace`/`oci_region` field or any cloud-specific concept. Provenance is
carried entirely in the manifest's `storage_location` field (`oci://bucket/prefix/object`, a
plain string), not in any canonical contract. Swapping OCI for S3/GCS later means changing the
runbook and the manifest's URI scheme — zero changes to `Call`, `Deal`, `Lead`, `ObjectionEvent`,
or `CallDealMatch`.

## Code added

`closer_ai.ingestion.profiling.summarize_capacity()` — the only code this branch adds. No OCI
SDK wrapper: the OCI CLI already covers everything the current workflow needs (list, download,
upload), and adding a Python dependency + wrapper module for that would be scope without
present value (see "What NOT to build yet"). If a repeated, scriptable OCI Python integration
becomes genuinely necessary later, `oci` (the official SDK) is the package to reach for then —
not built preemptively.

## Exact console/CLI setup steps

**Already executed** (compartment `ai-closer`, bucket `ai-closer-private` in `sa-saopaulo-1`,
versioning enabled, `NoPublicAccess`, 3 IAM groups, budget with 2 alert rules — all verified
2026-09-18 via read-only CLI checks). Kept below as the reference procedure for provisioning a
second environment later, not a pending TODO:

```bash
# 1. Compartment (console: Identity & Security > Compartments, or CLI)
oci iam compartment create --name ai-closer --description "AI Closer shared private data" \
  --compartment-id <tenancy-ocid>

# 2. Bucket (Standard tier, versioning ON, NoPublicAccess is already the default — verify, don't assume)
oci os bucket create --compartment-id <ai-closer-compartment-ocid> --name ai-closer-private \
  --versioning Enabled --public-access-type NoPublicAccess

# 3. Lifecycle rule: expire noncurrent versions after 30 days (console is easier for this step;
#    Object Storage > bucket > Lifecycle Policy Rules) — NOT YET CONFIGURED, follow-up item.

# 4. Groups + policies (console: Identity & Security > Domains > Groups, then Policies) — the
#    three groups (ai-closer-admins/ai-closer-business/ai-closer-ai) exist; only the admin
#    group's policy is attached so far (see "IAM" above) — the other two need their scoped
#    policy statements added before Gabriel/Otavio's accounts would have any real access.

# 5. Budget (console: Billing > Cost Management > Budgets) — done: $1 threshold, 2 alert rules active.

# 6. Prefixes are created implicitly on first upload (OCI Object Storage has no real
#    "folders" — a prefix exists the moment an object with that prefix is written).
```

## Exact first upload procedure (once authorization + storage decision + access review are all confirmed)

```bash
# Matheus, after the first 3-5 authorized Agro samples are received locally:
oci os object bulk-upload --bucket-name ai-closer-private \
  --src-dir ./local-private-staging/agro-sample-2026-09-18 \
  --object-prefix raw/agro/agro-sample-2026-09-18/

# Fill data/manifests/TEMPLATE.yaml -> data/manifests/agro-sample-2026-09-18.yaml (this IS
# committed to Git, per data/README.md — it's metadata only, never the raw data itself), then
# also upload it to OCI's manifests/ prefix as the durable, shared copy:
oci os object put --bucket-name ai-closer-private \
  --file data/manifests/agro-sample-2026-09-18.yaml \
  --name manifests/agro/agro-sample-2026-09-18.yaml

# Sync locally for validation (gitignored path, per data/README.md).
# --download-dir must be "data" (the object key already starts with "raw/...") — bulk-download
# recreates the FULL object key under --download-dir, so "data/raw/agro/" here would produce
# the wrong nested "data/raw/agro/raw/agro/<dataset_id>/..." path. Confirmed by smoke test.
oci os object bulk-download --bucket-name ai-closer-private \
  --prefix raw/agro/agro-sample-2026-09-18/ \
  --download-dir data

# Then continue with docs/data/REAL_CALL_VALIDATION_KIT.md's Execution Runbook, step 5 onward.
```

## What NOT to build yet

Lakehouse, Spark, Databricks, Airflow, a data catalog, a warehouse, Postgres/Supabase, FastAPI,
Kubernetes, streaming/event bus, MLflow, a feature store, a vector database, a dashboard, an
OCI Python SDK wrapper, Terraform. None of these has a real consumer yet for three people and a
double-digit number of files.

## Trigger for the next infrastructure layer

| Component | Add it when... |
|---|---|
| Database (Postgres/Supabase) | Manifest+file-based lookup genuinely can't answer a real question in reasonable time — e.g. Outcome Intelligence needs repeated joins across hundreds of Deal/Call records, not a handful of files. |
| Orchestration (Airflow etc.) | A multi-step pipeline becomes a *repeated*, not one-time, operation — e.g. real batch processing of the full 108+35 corpus on a recurring cadence, not the first-5-calls validation this kit is built for. |
| Data catalog | Enough datasets/snapshots (dozens+) that manual manifest lookup stops being fast enough for 3 people. |
| Terraform | More than one environment, or this manual setup needs to be reproduced a third time, or a 4th+ person needs repeatable onboarding. |
| Vector DB / feature store / MLflow | An actual embedding/ML-training workflow exists — `RuleBasedObjectionExtractor` is fully deterministic today, nothing here trains or embeds anything. |
| FastAPI / dashboard | A real consumer beyond these three people, using the CLI/manifests directly, needs self-serve access. |
| OCI Python SDK wrapper | The OCI CLI genuinely stops being sufficient for a *repeated* scripted operation — not before. |
