# The YouTube agent skill

Fourteen Claude skills that run a YouTube channel. The original eleven write scripts, packaging,
plans, and audits. Three more drive a **faceless** pipeline: render an MP4 + thumbnail, then upload
only after you say **ship it**.

**Content skills write. Nothing goes public until you approve.** `/yt-upload` is the only publisher,
and it refuses unless `STATUS=APPROVED`.

## Install

Paste this into Claude:

```
https://github.com/gaurav1999724/yt-app

Install this skill, then confirm /yt-script works.
```

Or do it yourself, in Claude Code:

```bash
git clone https://github.com/gaurav1999724/yt-app.git
cp -r yt-app/skills/yt-* ~/.claude/skills/
```

Or as a plugin:

```
/plugin marketplace add gaurav1999724/yt-app
/plugin install youtube-agent
```

Project-local instead of global: copy the same folders into your repo's `.claude/skills/`. No Claude
Code at all? Paste any single `SKILL.md` at the top of a chat and it runs as a mode. You lose the six
Python tools, which is most of the point of `/yt-script`, `/yt-retention` and `/yt-edit`, but the
rest works.

Then spend ten minutes on [`templates/voice.md`](templates/voice.md). Copy it to
`~/.claude/youtube/voice.md` and fill it in, or send Claude three of your own videos and say "write
my voice.md from these". Every skill reads that file. It matters more here than anywhere else.

## The fourteen

| command | what it does |
| --- | --- |
| `/yt-script` | One idea into a script. Five hooks off [21 formulas](skills/yt-script/hooks.json), scored, then the spoken script with the retention beats marked. |
| `/yt-package` | Title and thumbnail as one pairing, linted for truncation, duplication and vagueness. |
| `/yt-edit` | A transcript into an edit decision list: dead air, filler cues, retakes, with timecodes. |
| `/yt-comment` | The comment section triaged into four piles, then replies in your voice. Says which one to pin. |
| `/yt-plan` | A week that fits the hours you actually have. One anchor, one cheap one, three Shorts. |
| `/yt-viral` | What is working in your niche, ranked by multiple over each channel's own median. |
| `/yt-retention` | Your retention export read properly: hook leak, the cliffs, the slide, and what to change. |
| `/yt-shorts` | The Shorts already inside a long video, with a new first line written for each. |
| `/yt-seo` | The description, the tags that are worth having, and the three queries this should win. |
| `/yt-chapters` | Chapters from a transcript, validated against YouTube's own rules so they render. |
| `/yt-audit` | The whole channel, ending in ONE fix rather than twenty. |
| `/yt-pipeline` | End-to-end conductor: idea → script → package → SEO → render → stop for ship-it. |
| `/yt-render` | Faceless MP4: TTS + B-roll + captions + thumbnail. Sets `READY_FOR_REVIEW`. |
| `/yt-upload` | YouTube Data API upload. **Only** after you say ship it (`STATUS=APPROVED`). |

## The six tools

Every one of these runs on a clean Python 3 with no dependencies. They are the reason the skills are
not just prompts.

```bash
python3 skills/yt-script/hookscore.py --hook "one line"        # 5-property hook panel
python3 skills/yt-package/title.py --title "..." --thumb "..." # title + thumbnail linter
python3 skills/yt-edit/deadair.py transcript.srt               # edit decision list
python3 skills/yt-chapters/chapters.py transcript.srt          # validated chapters
python3 skills/yt-retention/retention.py retention.csv         # where they left, and why
python3 skills/yt-viral/swipe.py collected.json --min 2.0      # outliers by own-channel multiple
```

## Local UI (button clicks, no login)

A small local dashboard so you can run every step with buttons — no command pasting, no auth.

```bash
pip install -r pipeline/requirements.txt
python -m ui
```

Or double-click `start_ui.bat` on Windows. Open **http://127.0.0.1:8765**

Flow in the UI: **Create run → Save/edit → Render video → Approve (ship it) → Upload to YouTube**.

Binds to localhost only. Do not expose it to the public internet (there is no login).

## Faceless pipeline

Auto-generate a faceless video (no camera), review it, then upload when you approve.

### Setup

1. **Python 3.10+** and **FFmpeg** on your PATH.
2. Install pipeline deps from the repo root:

```bash
pip install -r pipeline/requirements.txt
```

3. Copy config and edit:

```bash
cp pipeline/config.example.env pipeline/.env
```

Set at least:

- `LANGUAGE` — `hi` (Hindi, default) or `en`
- `TTS_VOICE` — Hindi: `hi-IN-MadhurNeural` / `hi-IN-SwaraNeural` (`edge-tts --list-voices`)
- `VIDEO_FORMAT` — `shorts` (1080x1920) or `long` (1920x1080)
- `UPLOAD_PRIVACY` — keep `private` until you trust the pipeline
- `BROLL_PROVIDER` — default `pixabay` (UI can override per video to `unsplash`)
- `PIXABAY_API_KEY` — default B-roll source ([pixabay.com/api/docs](https://pixabay.com/api/docs/))
- `UNSPLASH_ACCESS_KEY` — optional alternate B-roll ([unsplash.com/developers](https://unsplash.com/developers))
- Without the chosen provider’s key, Hindi text-slide placeholders are used
- `YOUTUBE_CLIENT_SECRETS` — path to Google OAuth Desktop client JSON

4. Google Cloud: enable **YouTube Data API v3**, create an OAuth **Desktop** client, download JSON to
   `pipeline/client_secrets.json`. First upload opens a browser; token lands in `pipeline/token.json`.

### CLI

```bash
# Seed a run from fixture files (or your own script/package/seo)
python -m pipeline all-render \
  --idea "पहले 15 सेकंड रिटेंशन खत्म कर रहे हैं" \
  --script-file pipeline/fixtures/sample_script.md \
  --package-json pipeline/fixtures/sample_package.json \
  --seo-json pipeline/fixtures/sample_seo.json

# Review video.mp4 + thumb.png in the printed workspace/runs/<id>/ folder
# When ready:
python -m pipeline approve --from-dir workspace/runs/<id>
python -m pipeline upload --from-dir workspace/runs/<id>
```

Stages: `init` → `render` → (`STATUS=READY_FOR_REVIEW`) → `approve` → `upload`.

Each run folder holds `idea.json`, `script.md`, `package.json`, `seo.json`, `audio.mp3`,
`video.mp4`, `thumb.png`, `upload.json`, and `STATUS`.

Agent entry points: `/yt-pipeline` (conductor), `/yt-render`, `/yt-upload`.

### Approval gate

1. Render finishes with `READY_FOR_REVIEW`.
2. You watch the files. Last question: **ship it, or change it?**
3. Ship it → `approve` then `upload`. Change it → edit and re-render. No silent publishes.

## The fine print

**Upload is opt-in per video.** OAuth is yours. Unattended auto-upload is not supported.

**`hookscore.py` is a heuristic, not a predictor.** The panel was built and calibrated against 74
real short-form hooks (the first 15 seconds of auto-captions, top-8 and bottom-8 by views across
five channels). It separates deliberately bad hooks from real ones well. It separates a given
creator's hits from their own misses barely at all. A low score is a reason to look again; a high
score is not a promise.

**The formula classifier is about the words, not the result.** When `/yt-viral` says a title used
The Statistic, that is a judgement about the title you can see, not a claim about why the video got
its views.

**`/yt-viral` reads, it does not scrape.** Public listings only. It never logs in as you and never
touches your credentials.

**Tags barely matter** and this pack says so instead of selling you a tag generator.

**Nothing invents a number.** If a skill wants a figure it does not have, it asks you for it or
writes the line without it.

## Author

**Gaurav Kumar** — [github.com/gaurav1999724/yt-app](https://github.com/gaurav1999724/yt-app)

## Licence

MIT. Use it, change it, ship it.
