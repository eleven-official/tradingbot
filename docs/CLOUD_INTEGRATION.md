# Current Loki + cloud research

The existing Loki workspace now has **Cloud research** in its sidebar (`/#cloud-research`), including quick-search navigation. It uses the existing Loki login and visual components, displays cloud datasets/trials/certification, queues and pauses work, accepts licensed feature batches, and shows recorded cloud equity/positions/trades. Loaded cloud research is supplied to the existing copilot as explicitly read-only context. Local analogue bundles, account balances, runner controls and broker credentials are not overwritten, uploaded or automatically executed.

## Deployment topology

```text
Browser → existing Loki (FastAPI; existing Vercel project or desktop launcher)
             ├─ existing workspace, Auth, vault, research and broker tools
             └─ /api/account/research/{state,datasets,jobs,ingest}
                     ↓ signed server assertion; no browser-held bridge key
                 Loki cloud (Next.js; second Vercel project, root cloud/)
                     ├─ existing /api/* research APIs
                     ├─ GitHub Actions schedule → bounded optimizer/ingestion ticks
                     └─ the SAME Supabase Auth project and reviewed cloud tables
```

This combines the user experience and account identity without trying to run Next.js and FastAPI as one incompatible Vercel framework. Existing serverless-compatible Loki features can remain on Vercel. Existing **local-only** Python training/runner tools have not been ported into cloud workers by this integration. The new research optimizer itself is cloud-native and continues on its schedule without an open browser or local process.

## Configure

1. Choose one Supabase Auth project for both apps. For an existing Loki account to work, its **actual Auth UUID** must exist in that project. Matching emails in two unrelated projects are deliberately not treated as one identity. There is no email-based impersonation or automatic account migration.
2. Back up and review the target database. `cloud/schema.sql` is an initial schema, not a rerunnable migration. Its research table names differ from Loki's `loki_*` vault and `member_*` workspace tables, but check your actual schema for collisions before applying it to an existing project. Never rerun the initial schema blindly. For a new unified project, also install the existing account/vault schemas and explicitly migrate accounts/data as needed. The current production project received the initial research schema on 2026-11-01 after confirming that none of its research tables existed.
3. If you already installed the original cloud schema, review and apply only `cloud/migrations/001_research_bridge.sql` for the new nonce table/RPC. A fresh install of the current `cloud/schema.sql` already includes these. Run `cloud/tests/database.sql` only in a disposable project; it rolls back its synthetic records.
4. Deploy the `cloud/` directory as a second Vercel project using `cloud/README.md`. Keep Cron and market-data credentials there. Set its `NEXT_PUBLIC_SUPABASE_URL` to the same URL used by the existing Loki server's `SUPABASE_URL`.
5. Generate a new random shared secret of at least 32 characters. Set it on **both server deployments** as `LOKI_RESEARCH_BRIDGE_SECRET`. Do not put it in `NEXT_PUBLIC_*`, HTML, client JavaScript, localStorage, URLs or Git. This secret lets the trusted existing Loki server assert account identities; restrict access and rotate both deployments together if exposed.
6. On the **existing Loki server only**, set `LOKI_RESEARCH_URL=https://YOUR_CLOUD_PROJECT.vercel.app`. It must be the production HTTPS origin, without an API path, credentials, query or fragment. Outbound redirects are refused. Vercel deployment protection must allow server requests to these authenticated research routes; a protection-page response is not a successful connection.
7. Redeploy both projects (or restart the existing desktop launcher). Sign in to the current Loki, then choose **Cloud research**. No second browser login is needed. Creating a new dataset or queuing a campaign still requires `operator`/`admin` in `public.profiles`; login alone grants no paid compute rights. Use the role-grant SQL in `cloud/README.md` after checking the Auth UUID.

### Transport boundary

The existing server derives the UUID from its signed account cookie, validates a stale-tab owner header, and signs timestamp + random nonce + method + exact destination path + SHA-256 body digest + base64url identity. Assertions expire within 30 seconds. The cloud server verifies the HMAC with constant-time comparison, requires an identical Supabase project URL, consumes the nonce exactly once in PostgreSQL, and checks that the Auth user still exists and is not banned. No existing Supabase key, account cookie, access token or broker key is forwarded. The bridge never exposes the Cron endpoint or broker order endpoints.

Bridge calls use a server-role database client after authentication, so cloud read queries must always retain their explicit `user_id`/profile-ID predicates; browser sessions continue to use RLS. Mutations use the same existing cloud validation/role checks. CSRF checks remain on the existing Loki `/api/account/*` boundary. The shared secret trusts the existing server's cookie-signing/account security; it is not an untrusted public SSO provider.

Unknown network outcomes are not automatically retried as mutations. Refresh the cloud ledger before retrying. Cloud research errors do not stop or alter an existing paper/broker runner. Directly signing in to the standalone Next.js app creates its own browser session; the bridge itself creates none, and signing out of one independently opened app does not revoke an already-created session in the other.

## Data boundaries

- The 75% cloud certification protocol is not the same algorithm, embedding or artifact format as local analogue v3. Existing local bundles are **not** silently imported as certified cloud models.
- Cloud feature uploads require explicit chronological causal12 records and real option quote/Greek context where applicable. The upload widget accepts an array of up to 500 records under 900 KB, optionally seals the dataset, and does not approve provenance.
- Cloud trade/equity records are not the existing local paper account. No balance mirroring or model-to-order wiring is installed. Broker execution remains controlled solely by the original Loki controls.
- Cloud state in this integration is not saved into browser workspace autosave or the coding assistant's memory. It stays in the owner-scoped research tables.
- If the bridge is unconfigured, existing Loki remains usable and the Cloud research view displays setup instructions rather than fabricated results.

## Verify before rollout

Run Python regression tests, cloud unit tests/typecheck/build, and database SQL checks in a disposable Supabase project. Then test two actual users, researcher/operator distinctions, nonce replay rejection, deleted/banned accounts, signature/body tampering, cloud outages, session expiry and normal existing paper controls. Mocked tests and a passing production build do not establish that the live bridge has been deployed or its schema applied.

From the repository root:

```bash
python -m pytest --no-cov
```

From `cloud/`:

```bash
npm ci
npm test
npm run typecheck
npm run build
```

Cloud tests include a jsdom smoke test of the actual existing-workspace script:
guest/setup states, researcher restrictions, loading through the account bridge
and creating research with the active Loki stock symbol. They also assert
explicit owner predicates on every cloud service-role state query. The SQL
script checks nonce replay rejection in addition to the original database gates;
syntax parsing alone is not equivalent to executing those checks in PostgreSQL.
