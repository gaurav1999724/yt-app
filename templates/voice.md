# voice.md

Copy this to `~/.claude/youtube/voice.md` and fill it in. Every skill in this pack reads it. Ten
minutes here is worth more than any prompt you will ever write, because on YouTube you have to say
the words out loud and a script in the wrong voice is unreadable on camera.

## Who I am talking to

One person. Name them properly - not "creators", but "someone with under a thousand subs who has
made nine videos and cannot work out why none of them break 400 views".

## How I actually talk

Paste the transcript of your best-performing video here, or three of them. Not what you wish you
sounded like.

## Words I never use

The ones that are not mine. Be specific: "unlock", "game-changer", "dive in", "let's get into it".

## Words I do use

Your tics. The phrases that are yours. Keep them.

## What I will not claim

Numbers I cannot show, results that are not mine, tools I have not used. Write them down so the
skills refuse them for you instead of you catching it in the edit.

## My format

Length, how a video opens, whether there is an intro, whether you swear, whether you appear on
camera, what the desk looks like.

## Faceless pipeline

Fill this in if you use `/yt-pipeline` / `/yt-render` (auto TTS + B-roll, no camera).

- **Language:** `hi` (Hindi) by default. Scripts, titles, SEO in Hindi.
- **Niche:** one sentence.
- **Cadence:** e.g. 3 Shorts / week.
- **Preferred length:** `shorts` (vertical) or `long` (16:9). Match `VIDEO_FORMAT` in `.env`.
- **TTS voice:** Hindi — `hi-IN-MadhurNeural` (male) or `hi-IN-SwaraNeural` (female). List: `edge-tts --list-voices`.
- **B-roll:** Unsplash (`UNSPLASH_ACCESS_KEY`). Without key, Hindi text slides are used.
- **Brand colors:** background / foreground / accent hex for thumbnails.
- **Default privacy after ship-it:** `private` (recommended), `unlisted`, or `public`.
