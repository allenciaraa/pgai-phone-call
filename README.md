# PGAI Voice Bot

This is my submission for the Pretty Good AI engineering challenge — a voice bot that calls PGAI's test line, pretends to be a patient, and has a real spoken conversation with their AI agent so I can hear how it handles things like scheduling, refills, and questions it isn't expecting.

## Stack

There are a few services stitched together here, each doing one job:

- **Twilio** actually places the phone call and streams the live audio back and forth over a WebSocket.
- **[Pipecat](https://pipecat.ai)** is the framework that wires everything else together into a pipeline: it takes the caller's audio, sends it to **Deepgram** to turn into text, hands that text to **Claude** (which is playing the "patient" and decides what to say back), and sends Claude's reply to **Cartesia** to turn into speech that gets played into the call.
- Each call uses one of several scripted "patients" I wrote (in `bot/scenarios.py`) — basically a short description of who's calling and what they want, like "you're Linda, you need to reschedule your Thursday appointment to next week." I pick which one to use when I start a call.
- Twilio records the whole call for me, and I also build a text transcript on my end as the conversation happens, so every call ends up with a matching recording + transcript saved locally.
- Since my computer doesn't have a public address Twilio can reach, I run a tunnel (ngrok) that gives it one temporarily.

## Set Up

1. Create a virtual environment and install everything:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your own API keys (Twilio, Deepgram, Anthropic, Cartesia).

3. Start a tunnel so Twilio can reach your computer:
   ```bash
   ngrok http 8000
   ```
   Grab the `https://....ngrok-free.app` URL it gives you and paste it into `PUBLIC_SERVER_URL` in your `.env`. Heads up — this URL is different every time you restart ngrok, so you'll need to update `.env` again if you stop and restart it later.

That's the one-time setup. From here on it's really just two things: **start the server, then make calls.**

## Run

**Start the server.** This is the program that actually answers Twilio's questions and runs the conversation pipeline. Leave this running in its own terminal window:

```bash
uvicorn bot.server:app --reload --port 8000
```

Wait until you see `Application startup complete` in the uvicorn log before doing anything else.

**Make calls.** In a second terminal, you've got two options depending on what you're trying to do:

- **One call at a time** — good for testing a specific scenario:

  ```bash
  python -m bot.call schedule_appointment
  ```

  Swap `schedule_appointment` for any scenario name from `bot/scenarios.py`. If you don't specify one it'll default to `schedule_appointment`.

- **The whole batch, automatically** — runs every scenario one after another, waiting for each call to actually finish before starting the next:
  ```bash
  python -m bot.run_batch
  ```

## Transcript & Recordings

Every call saves two files, both named after Twilio's call ID so they're easy to match up:

- `calls/recordings/<call id>.mp3` — the audio
- `calls/transcripts/<call id>.txt` — what was said, both sides

## Notes

- There's a hard time limit on every call (`MAX_CALL_SECONDS` in `.env`) so that if something ever goes wrong and the conversation gets stuck, it can't run forever and rack up charges. I have it set to a few minutes.

## File Organization

```
bot/
├── server.py       # the server Twilio talks to, runs the actual conversation pipeline
├── call.py         # places one call for a given scenario
├── run_batch.py    # runs every scenario, one after another
└── scenarios.py    # the patient personas, who's calling and what they want
calls/
├── recordings/     # saved call audio
└── transcripts/    # saved call transcripts
docs/
├── architecture.md # a bit more on how/why I built it this way
└── bug_report.md   # bugs I found in PGAI's agent while testing
```
