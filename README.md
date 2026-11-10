# BhashaCode — Explain code in Indian languages

Paste a code snippet, pick a language, get a clear plain-language
explanation of what the code does, plus a short line-by-line breakdown.

Solo entry by **Aarambh Maan Shrestha** (GitHub: Duke2nuke) for the
**BharatCode Build League** — register/submit by **10 Nov 2026, 11:59 PM IST**.
First prize ₹10,000. Category: Coding & developer tools.

## Languages

English, Hindi, Tamil, Telugu, Bengali, Marathi, Kannada, Malayalam,
Gujarati, Punjabi. Code, function names and keywords stay in English,
untranslated, so the explanation can still be followed against the code.

## How to run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000
```

Endpoints:

- `GET /` — the one-page form (code textarea, language dropdown, result area)
- `POST /explain` — form post returns the page with the result; send JSON
  (`{"code": "...", "language": "hi"}`) to get JSON back
- `GET /health` — `{"status": "ok", "mode": "mock"|"live"}`

## BharatCode API key (live mode)

Get a key at https://bharatcode.ai/account (BharatCode homepage:
students get Qwen free up to 10M tokens a day), then:

```bash
export BHARATCODE_API_KEY=your-key-here
python app.py
```

The key is read from the environment only — never hardcoded, never
committed (see `.env.example` for the placeholder shape). Optional
overrides: `BHARATCODE_API_URL` (default
`https://bharatcode.ai/api/model/v1`), `BHARATCODE_MODEL` (default
`qwen-3.8-27b`).

## Honest mock-mode note

With no key set, the app still runs end to end and returns a
deterministic local explanation, clearly labelled everywhere it appears:

> MOCK — no BharatCode key set, demo only

Mock explanations are in English (the language choice is honoured by
the live model; without a key there is no translator to call). A mock
result is never presented as a live model result.

## BharatCode API — what was verified

Source: the Build League example project Marg
(https://github.com/Mqhnish/marg — `marg/llm.py`, `BharatCode.txt`,
read 2026-11-06). No standalone BharatCode API docs page was found
that day; Marg is the documented reference, and bharatcode.ai confirms
Qwen 3.8 27B is API-available.

- Base URL: `https://bharatcode.ai/api/model/v1`
- Default model: `qwen-3.8-27b`
- Endpoints: `POST /responses` (Marg default, `store=false`) and
  `POST /chat/completions` (Marg `--api chat`). BhashaCode uses
  Chat Completions for its single-turn explain call — same base URL
  and model.
- Auth: `Authorization: Bearer $BHARATCODE_API_KEY`
- Retries on 429/5xx (BharatCode returns 503 when the model is busy)

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests cover the mock explain path, language handling, empty-code
validation, and the API client with a fake transport — no key or
network needed.

## Files

| File | What it is |
| --- | --- |
| `app.py` | Flask app: `/`, `/explain`, `/health` |
| `bharatcode_client.py` | BharatCode API client + mock fallback |
| `templates/index.html` | One-page form and result view |
| `BharatCode.txt` | Project + BharatCode API usage, as in the Marg example |
| `tests/test_bharatcode.py` | Unit tests (mock, validation, fake-transport client, Flask app) |
| `requirements.txt` | Flask |
| `.env.example` | Key placeholder only |

## BharatCode Build League submission note

Registration only was in progress at build time (BharatCode sign-in
was still being resolved in the parent chat). This repo is the project
to submit by 10 Nov 2026, 11:59 PM IST — no project was submitted
from this build step.
