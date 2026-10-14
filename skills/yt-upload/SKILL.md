---
name: yt-upload
description: >-
  Upload an approved faceless pipeline run to YouTube via the Data API.
  Use only after the user says ship it / approve / upload it, never
  unprompted. Refuses if STATUS is not APPROVED.
---

# yt-upload

Publishes. Only after the human ships it.

## Hard rule

1. Read `workspace/runs/<run_id>/STATUS`.
2. If it is not `APPROVED`, do **not** upload. If they just said "ship it", run approve first.
3. Never invent approval. Silence is not approval.

```bash
python -m pipeline approve --from-dir workspace/runs/<run_id>
python -m pipeline upload --from-dir workspace/runs/<run_id>
# optional: --privacy private|unlisted|public
```

Default privacy comes from `UPLOAD_PRIVACY` in `.env` (recommend `private` until they trust the pipeline).

## One-time Google setup

1. Google Cloud project → enable **YouTube Data API v3**
2. OAuth consent screen + Desktop client → download JSON
3. Save as `pipeline/client_secrets.json` (or path in `YOUTUBE_CLIENT_SECRETS`)
4. First upload opens a browser for OAuth; token saved to `pipeline/token.json`

## What to hand back

- The watch URL from `upload.json`
- Privacy status used
- Reminder: thumbnail may need channel verification for custom thumbs on brand-new channels

## The gate

If they have not said ship it (or equivalent), stop and ask. Do not upload "to be helpful".
