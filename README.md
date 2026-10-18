just a small thing to get hacker news in small format.

<br></br>

## How:
- A GitHub Action ticks hourly (`.github/workflows/digest.yml`)
- `hn_digest.py` has a time guard: it only runs at 15:00.

## What:
- Top front-page stories collected from the HN Algolia API
- The Mistral chat API turns them into highlights and per-story
  summaries, saved as `<month>-<year>/<dd-mm-yyyy>.md`

## Setup:
1. Add a `MISTRAL_API_KEY` secret under Settings → Secrets and
   variables → Actions
2. Optional env vars: `MAX_STORIES`, `TOP_PICKS`, `DIGEST_MODEL`,
   `DIGEST_LANGUAGE`
