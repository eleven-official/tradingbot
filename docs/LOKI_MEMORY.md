# Loki-only Obsidian memory

Loki's local chat stores explicit notes as Markdown. OpenCode no longer loads
the old project-memory notes automatically. The old `Obsidian-memory` folder
is not Loki's runtime memory; it remains untouched as a historical archive.

## Connect Loki and Obsidian

1. Run Loki through its local launcher and open its chat.
2. In Obsidian choose **Open folder as vault** and select
   `tradingbot/state/loki_memory`. Send the first `remember` message to create it.
3. In Loki chat send `remember I prefer reviewing paper results weekly`.
4. Send `recall weekly` or `show memory`. Loki reads the saved notes after
   browser/server restarts. Obsidian edits to `loki-note-*.md` appear on recall.

For an existing vault set the server environment variable `LOKI_MEMORY_DIR`
to a dedicated subfolder, then relaunch Loki. Only `loki-note-*.md` files in
that folder are read, not your whole vault. No Obsidian plugin/API key is needed.
Recall returns at most five matches; storage is limited to 1000 notes.

Memory is for the single local operator, guarded by the launcher's local token.
It is unavailable to remote/public chat clients. It does not automatically save
chat transcripts, train the model, submit orders or alter risk gates. Loki's
current chat is a deterministic coach, not an externally hosted LLM.

Keep notes free of credentials. Basic credential-pattern rejection is not a
complete secret scanner. Notes are plaintext, and OneDrive may sync this folder.
Remove/archive notes through Obsidian. Supabase logging is a separate service;
these notes are not automatically uploaded to the database.
