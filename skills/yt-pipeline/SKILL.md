---
name: yt-pipeline
description: >-
  Run the full faceless YouTube pipeline end to end - plan or viral idea,
  script, package, SEO, render - then stop for ship-it approval before
  upload. Use for "run my channel", "auto generate a video", "faceless
  pipeline", "make and prepare an upload".
---

# yt-pipeline

Conductor. Existing skills write. `yt-render` builds the file. `yt-upload` publishes only after ship-it.

## Before anything

1. Read `~/.claude/youtube/voice.md` (or `templates/voice.md`). Faceless fields matter: niche, format (shorts/long), Hindi TTS voice, brand colors, default privacy.
2. Ensure `pipeline/.env` exists (from `pipeline/config.example.env`), FFmpeg on PATH, and `pip install -r pipeline/requirements.txt`. Default language is **Hindi** (`LANGUAGE=hi`, `TTS_VOICE=hi-IN-MadhurNeural`). B-roll uses **Unsplash** (`UNSPLASH_ACCESS_KEY`).
3. Write script, title, thumbnail text, and SEO in Hindi unless the user asks for another language.
4. Never invent numbers, results, or sources.

## Stages (in order)

1. **Idea** — `/yt-viral` and/or `/yt-plan`. Pick one idea that fits the voice and hours.
2. **Script** — `/yt-script`. Keep ON SCREEN cues on every beat. Score hooks with `hookscore.py`.
3. **Package** — `/yt-package`. Lint title + thumb text with `title.py`. Write `package.json`:
   ```json
   {"title":"...","thumbnail_text":"THREE WORDS","thumbnail_brief":"..."}
   ```
4. **SEO** — `/yt-seo` (and chapters if long-form). Write `seo.json` with `description`, `tags`, `category_id`.
5. **Init run folder**
   ```bash
   python -m pipeline init --idea "..." --script-file script.md --package-json package.json --seo-json seo.json
   ```
   Capture the printed path as `RUN_DIR`.
6. **Render** — `/yt-render` / `python -m pipeline render --from-dir RUN_DIR`
7. **Stop.** Show title, paths, runtime. Last line: **ship it, or change it?**
8. **Only if they ship it** — `/yt-upload`:
   ```bash
   python -m pipeline approve --from-dir RUN_DIR
   python -m pipeline upload --from-dir RUN_DIR
   ```

Shortcut when files are already written:

```bash
python -m pipeline all-render --idea "..." --script-file script.md --package-json package.json --seo-json seo.json
```

## After a successful upload

Optional: `/yt-shorts` on the new transcript for follow-up Shorts (separate runs). Do not auto-upload those either.

## What this will not do

- Upload without approval
- Appear on camera
- Scrape logged-in YouTube
- Reply to comments unattended (use `/yt-comment` when asked)

## The gate

Every pipeline run ends at review unless the user already said ship it in the same turn after seeing the render. Prefer showing the files first.
