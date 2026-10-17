# HN Digest (GitHub Action)

A small GitHub Action that fetches the day's top Hacker News stories every afternoon, summarizes them with a Mistral model, and commits an Obsidian-ready markdown note to this repository. With the Obsidian Git plugin in your vault, the note syncs down automatically, so a fresh digest is waiting when you open Obsidian.

Everything runs on GitHub's infrastructure for free. The only cost is the Mistral model call, which draws from your plan's included monthly usage, not from pay-as-you-go credits.

## What happens in a run

The workflow runs hourly, but the script exits immediately unless the local time in Europe/Brussels is 15:xx. So the real digest happens once a day, at 15:00 your time, and the hourly tick makes it immune to daylight saving changes. When it runs for real, the script:

- fetches the Hacker News front page through the official HN search API and sorts by points
- fetches, best effort, the article pages themselves, so summaries build on real text
- sends the batch through a Mistral model (default `mistral-small-latest`), which returns the highlights plus a summary per story
- writes the note into the `HN Digest` folder, with YAML frontmatter (date, tags), a "Today's highlights" section, and one section per article with a "Why it matters" line
- commits and pushes the note, in the workflow's final step

Summaries are written in the language from `DIGEST_LANGUAGE` in the workflow file, English by default.

## Setup

**Create the repository.** Create a new repository on GitHub, for example `hn-digest`, and make it private so your notes stay yours. Upload the files from this project through the GitHub web interface ("Add file" then "Upload files"), including the hidden `.github` folder. The folder structure must be kept as is, since GitHub only recognizes workflows under `.github/workflows`.

**Add your Mistral API key.** In the repository, open Settings, Secrets and variables, Actions, and create a new repository secret named `MISTRAL_API_KEY`. Paste the key from console.mistral.ai (API keys section). The key is then available to the workflow without ever being visible in the files.

**Enable Actions.** Open the Actions tab in the repository and confirm that workflows are enabled if GitHub asks.

## Test it right now

You do not need a terminal for this. In the repository, open the Actions tab, select "HN digest" in the list on the left, click "Run workflow", then "Run workflow" again. A run appears at the top: click it and watch each step. When it finishes green, open the `HN Digest` folder in the repository: the note for today should be there, committed by hn-digest-bot. Manual runs always execute, regardless of the time of day.

If the run fails, open the failing step and read the log line at the bottom. The most common causes: a missing or misspelled `MISTRAL_API_KEY` secret, or exhausted included usage on your Mistral plan.

## Obsidian Git setup

Inside your Obsidian vault:

- Clone the repository into a folder and open that folder as your vault, or clone it into a subfolder of an existing vault
- Install the community plugin **Obsidian Git** and configure it with a personal access token that has read and write access to the repository (Settings, Developer settings, Fine-grained tokens on GitHub)
- Set the plugin to pull on startup and on a fixed interval, for example every 15 minutes

From then on, the daily note appears in the `HN Digest` folder of your vault automatically.

## Adjusting things

- **Run time**: edit the hour check in `hn_digest.py` (currently `15`) to move the digest, for example to 9 for a morning note
- **Story count and language**: `MAX_STORIES`, `TOP_PICKS` and `DIGEST_LANGUAGE` are set in the workflow file and can be changed there
- **Model**: set `DIGEST_MODEL` in the workflow file, for example to a larger model for richer summaries

## Costs and limits

- GitHub Actions: free for public repositories; private repositories get 2000 free minutes per month. This job uses about 2 minutes per day, roughly 60 per month, well inside the free tier
- Mistral: one chat call per day with a few thousand tokens on `mistral-small-latest`, drawing from the plan's included monthly usage
