# reelbot: Facebook Reels automation (psychology facts)

One command takes you from **idea → script → image prompts → voiceover → video prompts → 1-minute vertical video → review → posted Reel**.

```
python -m reelbot run
💡 Generating ideas...          Claude suggests 10 fresh topics (skips ones in history.json)
✍️  Writing script: ...          Claude writes 6-8 scenes: narration, on-screen text, image + video prompts, caption, hashtags
🎙️  Voiceover...                 Edge TTS (free) + word timings
🖼️  Images...                    Flux schnell on fal.ai (~$0.003/image) or Pollinations (free)
🎬 Rendering...                  ffmpeg: Ken Burns motion, crossfades, word-by-word captions, optional music
Post it? [y]es / [n]o / [r N]   review, regenerate any scene image, then publish to your Page
```

Cost is about **$0.05 per Reel**: two Claude calls plus 7-8 images. The voice is free.

## Setup

1. Install Python 3.11+ and **ffmpeg** (`brew install ffmpeg`, `sudo apt install ffmpeg`, or `winget install ffmpeg`).
2. Install dependencies and create your `.env`:
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   ```
3. Fill in `.env`:
   - `ANTHROPIC_API_KEY`: from https://console.anthropic.com
   - `FAL_KEY`: from https://fal.ai/dashboard/keys. Not needed if you set `images.provider: pollinations` in `config.yaml`.
   - `FB_PAGE_ID` and `FB_PAGE_TOKEN`: see below.
4. Optional: drop royalty-free `.mp3` tracks into `assets/music/`. One is picked at random and mixed under the voice.

### Getting a Facebook Page token

1. Create an app at https://developers.facebook.com/apps (type **Business**).
2. Open the **Graph API Explorer**, select your app, and add these permissions: `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `publish_video`. Then click **Generate Access Token**.
3. Exchange it for a long-lived user token:
   `GET https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN`
4. Call `GET https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_USER_TOKEN`. Copy your Page's `id` into `FB_PAGE_ID` and its `access_token` into `FB_PAGE_TOKEN`. A Page token made from a long-lived user token doesn't expire.

While the app is in development mode, posting works for Pages you admin. Reels must be 3-90 s, 9:16, and at least 540x960; reelbot outputs 1080x1920 at 30 fps, under 60 s.

**AI labeling:** captions end with the `publish.ai_disclosure` line from `config.yaml`. Meta may also apply its own "AI info" label.

## Usage

| Command | What it does |
|---|---|
| `python -m reelbot run` | Full pipeline, then the review prompt, then post |
| `python -m reelbot run --choose` | Pick from the 10 generated ideas yourself |
| `python -m reelbot run --topic "the Zeigarnik effect"` | Skip idea generation |
| `python -m reelbot make` | Generate only (no posting) |
| `python -m reelbot review output/<folder>` | Review an earlier Reel: post it or regenerate scenes |
| `python -m reelbot post output/<folder>` | Post an approved Reel |
| `python -m reelbot rerender output/<folder>` | Re-render after swapping images, music, or caption style |
| `python -m reelbot make --dry-run` | Bundled sample script (no Claude call), real voice and images |
| `python -m reelbot make --offline` | Sample script, placeholder images and a silent track. Needs no keys or network; good for checking ffmpeg and caption layout. |

Everything for a Reel lands in `output/<date>-<slug>/`:
- `script.json`: narration plus the image and video prompts for every scene
- `voice.mp3` and `words.json`
- `scene_NN.jpg`
- `captions.ass`
- `reel.mp4` and `preview.jpg`
- `meta.json`: status and the Facebook video id

Posted topics are recorded in `history.json`, so ideas never repeat.

## Customizing (`config.yaml`)

- **Niche, audience, tone:** change `niche` to run any faceless page (history, finance tips, and so on).
- **Voice:** `voice.name` can be any Edge voice (`edge-tts --list-voices`). Raise `voice.rate` if scripts run long.
- **Look:** `images.style` is appended to every image prompt. `captions.*` controls the font, size and position.
- **Model:** `llm.model` defaults to `claude-opus-5-5` at `effort: low`. Set `claude-sonnet-5-5` to make it cheaper still.
- **AI video later:** every scene already has a `video_prompt` (camera and subject motion). That's ready for image-to-video models (Kling or Seedance on fal.ai) if you outgrow Ken Burns.

## Scheduling

Generation is unattended; posting waits for your review. A common rhythm:
- Run `python -m reelbot make` from cron each morning.
- Run `python -m reelbot review output/<folder>` when you're ready to approve.

## Tests

```bash
python -m pytest -q
```
