---
name: yt-render
description: >-
  Render a faceless YouTube video from an approved script and package -
  TTS voiceover, B-roll, burned captions, and thumbnail PNG. Use for
  "render this", "make the video", "generate the mp4", "faceless render",
  or after yt-script and yt-package are ready.
---

# yt-render

Turns write-ups into files. Does not upload.

## Inputs (in a run folder)

Required under `workspace/runs/<run_id>/`:

- `script.md` — spoken script with `[ON SCREEN: ...]` cues per beat
- `package.json` — at least `title` and `thumbnail_text` (max three words)

Optional: `seo.json`, `idea.json`.

If the user only pasted a script in chat, create a run first:

```bash
python -m pipeline init --idea "working title" --script-file path/to/script.md --package-json path/to/package.json
```

Copy `pipeline/config.example.env` to `pipeline/.env`. Defaults are Hindi:
`LANGUAGE=hi`, `TTS_VOICE=hi-IN-MadhurNeural`. Optional: `UNSPLASH_ACCESS_KEY` for real
photo B-roll. Scripts should be written in Hindi. FFmpeg must be on PATH.

## Render

```bash
python -m pipeline render --from-dir workspace/runs/<run_id>
```

That produces `audio.mp3`, `video.mp4`, `thumb.png`, `captions.srt`, and sets `STATUS=READY_FOR_REVIEW`.

## What to hand back

- Absolute paths to `video.mp4` and `thumb.png`
- Title + thumbnail text from `package.json`
- Runtime from `video.meta.json`
- Remind them to watch the file before shipping

## The gate

Nothing here publishes. Last line of every run:

**ship it, or change it?**

On "ship it" → `/yt-upload` (approve then upload). On "change it" → edit script/package and re-render. Do not call upload until they approve.
