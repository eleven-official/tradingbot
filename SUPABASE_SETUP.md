# Supabase private vault

The advanced terminal and `LokiSupabaseManager` share
`loki_v8.persistence.SupabaseLogger`. No Supabase SDK/browser service key is
required. Missing configuration leaves logging disabled.

1. Inspect and run `supabase_schema.sql` in your project's SQL editor. It creates
   six vault tables, enables RLS and revokes browser-role access. It also hardens
   existing installations of these tables. Revoked grants block older browser
   policies from exposing global records.
2. Set these variables on the Loki server, outside source control:

   ```dotenv
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_SERVICE_KEY=sb_secret_your_server_secret
   ```

3. Restart the local launcher. Open Advanced terminal → Data Vault → Test
   Connection. It reads at most one ID from `loki_events`, writing no sample
   trade. Status remains unverified until an actual successful request; key/URL
   rotation invalidates verification.
4. Start a paper loop explicitly or run research to produce actual records.
    Logging uses a bounded background queue, redacted errors and failure cooldown.

## Website accounts and autosave

Run `supabase/schema_member_data.sql` for private per-user workspaces, then
`supabase/schema_workspace_autosave.sql` for atomic partial autosaves. See
`docs/ACCOUNT_STORAGE.md` for session lifetime, save/restore behavior, deployment
configuration and security limits. Local `.env` values do not configure Vercel
or another deployed host automatically.

Keep server secrets in private environment settings and rotate any key exposed
in chat. Do not disable RLS or grant browser roles access to these private tables.

Opaque `sb_secret_` keys use only `apikey`. Legacy `service_role` JWTs also use
`Authorization: Bearer`. Publishable/anon keys are rejected for this vault.
Requests require an HTTPS `*.supabase.co` origin and never follow redirects.
Custom/self-hosted origins need a reviewed transport configuration change.

The service role bypasses RLS. Keep it out of browser code, screenshots, chat,
logs and `NEXT_PUBLIC_*` variables. This global vault is not a multi-user API;
customer authentication and owner-scoped policies are separate requirements.

Mocked tests verify the implementation. Checking your hosted project requires
configured server credentials and an applied schema.

## Cloud research in the existing Loki workspace

See [docs/CLOUD_INTEGRATION.md](docs/CLOUD_INTEGRATION.md) for adding the Next.js
optimizer to the current Loki sidebar and login. Both servers must share the
same Supabase Auth project. The bridge uses a separate server-only signing
secret; do not copy existing vault credentials into browser code or disable
RLS. Review the additive research schema before touching an existing project.

Official references: [API keys](https://supabase.com/docs/guides/getting-started/api-keys),
[new-key migration](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys),
[row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security).
