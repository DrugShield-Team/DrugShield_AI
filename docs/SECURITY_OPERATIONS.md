# Security and operations baseline

DrugShield is a simulation-only decision-support prototype. This baseline reduces
risks for local team use; it is not a certification for use with real investigations
or a substitute for a security review.

## Identity and access

- API routes require a configured account. Roles are simulator, reviewer, and
  admin; only reviewers/admins can read cases, graphs, or evidence attachments.
- Review decisions take the username from the authenticated principal. Clients
  cannot choose the reviewer identity in a request body.
- Sessions use a short-lived, HttpOnly, SameSite=Strict cookie. Production sets
  Secure; production mode redirects HTTP to HTTPS.
- User records contain PBKDF2-SHA256 password hashes, not passwords. Login
  attempts are throttled per source address in the API process.
- Configure exact browser origins in DRUGSHIELD_CORS_ORIGINS; do not use a wildcard.

## Evidence privacy

- Database event text, analysis results, reports, and reviewer notes are encrypted
  with AES-256-GCM. Uploaded evidence images are also AES-GCM encrypted at rest.
- The API decrypts images into a short-lived OS temporary directory for analysis
  and removes that directory after analysis. Keep the host's temporary storage
  protected and monitored.
- The encryption key is separate from the database and evidence files. Backups
  cannot be read without the original key. Keep a protected offline copy of it.
- Legacy plaintext database fields and files referenced by stored events are
  encrypted when the API starts with the key configured. Orphan image files in
  runtime/raw that have no database reference are not automatically discovered;
  review and securely remove or migrate those separately.
- The evidence endpoint returns downloaded bytes with no-store and nosniff.

## Retention and backups

- Default retention is 90 days (DRUGSHIELD_RETENTION_DAYS). Cleanup previews
  only unless --apply is explicitly passed.
- Run python scripts/retention_cleanup.py to preview; schedule
  python scripts/retention_cleanup.py --apply using the host's trusted scheduler
  after reviewing the policy.
- Run python scripts/backup_runtime.py for a SQLite-consistent snapshot and a
  copy of referenced encrypted evidence. The backup tool does not prune old
  backups; enforce a retention policy on the protected backup destination.
- Periodically test restore in an isolated environment with the encryption key.
  This repository does not automate off-site backup storage or restore.

## Monitoring and deployment

- /api/v1/health is a liveness endpoint; /api/v1/ready checks SQLite readiness.
- /api/v1/metrics requires admin and exposes process-local request/error and
  analysis-time counters. These counters reset on restart; they are not a
  replacement for durable monitoring or alerting.
- Logs contain request ID, method, path, status, and duration, not message bodies,
  passwords, tokens, or evidence contents.
- Docker runs as an unprivileged user, drops Linux capabilities, uses a read-only
  root filesystem, and publishes the API only on loopback. Do not expose this
  compose setup directly to the internet.
- For a real deployment, terminate TLS at a maintained reverse proxy, configure
  trusted proxy behavior, use managed secret storage and encrypted off-host
  backups, set strict host/origin allowlists, add durable monitoring/alerts, and
  obtain a security/privacy review. Do not switch to DRUGSHIELD_ENV=production
  without HTTPS termination in front of the API.

## Key rotation and loss

Changing DRUGSHIELD_DATA_ENCRYPTION_KEY makes existing encrypted records and
attachments unreadable. Back up first and perform a planned decrypt/re-encrypt
migration; no automatic key rotation is implemented. Losing the key means losing
access to encrypted evidence. Keep it separate from backups and restrict access.
