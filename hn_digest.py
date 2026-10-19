import asyncio
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"

MAX_STORIES = int(os.environ.get("MAX_STORIES", "12"))
TOP_PICKS = int(os.environ.get("TOP_PICKS", "3"))
DIGEST_MODEL = os.environ.get("DIGEST_MODEL", "mistral-small-latest")
DIGEST_LANGUAGE = os.environ.get("DIGEST_LANGUAGE", "English")

ARTICLE_TEXT_LIMIT = 2500
MAX_ARTICLE_FETCH_CHARS = 20000
FETCH_CONCURRENCY = 5

SYSTEM_PROMPT = (
    "You are a technology editor writing a short daily digest of Hacker News."
    "You receive titles, points, comment counts and optional excerpts of article text. "
    "Reply only with valid JSON without code fences, using the fields 'highlights' and 'stories'."
)


async def fetch_stories() -> list[dict]:
    params = {"tags": "front_page", "hitsPerPage": 40}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(HN_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()

    hits = data.get("hits", [])
    hits.sort(key=lambda h: h.get("points") or 0, reverse=True)
    return hits[:MAX_STORIES]


def _html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


async def enrich_with_article_text(stories: list[dict]) -> list[dict]:
    """Fetch the article page for each story, best effort. Errors are ignored."""
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch_one(story: dict) -> dict:
        url = story.get("url")
        if not url:
            return story
        try:
            async with semaphore:
                async with httpx.AsyncClient(
                    timeout=20,
                    follow_redirects=True,
                    headers={"User-Agent": "hn-digest-action/0.1"},
                ) as client:
                    response = await client.get(url)
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return story
            text = _html_to_text(response.text[:MAX_ARTICLE_FETCH_CHARS])
            if text:
                story["article_text"] = text[:ARTICLE_TEXT_LIMIT]
        except Exception:
            pass
        return story

    return list(await asyncio.gather(*(fetch_one(s) for s in stories)))


async def summarize(api_key: str, stories: list[dict], note_date: str) -> dict:
    """Send the stories to the Mistral chat API and get a structured digest."""
    payload = [
        {
            "title": s.get("title"),
            "url": s.get("url"),
            "points": s.get("points"),
            "comments": s.get("num_comments"),
            "article_excerpt": s.get("article_text"),
        }
        for s in stories
    ]

    user_prompt = (
        f"Here are today's Hacker News stories (date {note_date}):\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return JSON in this shape:\n"
        "{\n"
        '  "highlights": ["..."],\n'
        '  "stories": [\n'
        '    {"title": "...", "summary": "...", "why_it_matters": "..."}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        f"- highlights contains {TOP_PICKS} short sentences, one for each of "
        "the most important points across today's stories, at most 20 "
        "words each.\n"
        "- stories follows the same order as the input, one entry per story.\n"
        f"- summary is 2-3 sentences written in {DIGEST_LANGUAGE}, readable "
        "for a developer.\n"
        f"- why_it_matters is 1 sentence in {DIGEST_LANGUAGE} explaining why "
        "the story matters.\n"
        f"- Write in {DIGEST_LANGUAGE}, but keep technical terms and "
        "product names as they are.\n"
    )

    request = {
        "model": DIGEST_MODEL,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        response = httpx.post(
            MISTRAL_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=request,
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"Mistral API returned {exc.response.status_code}:")
        print(exc.response.text[:2000])
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"Request to the Mistral API failed: {exc}")
        sys.exit(1)

    data = response.json()
    raw = data["choices"][0]["message"]["content"] or ""

    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print("Model reply was not valid JSON, exiting with failure.")
        print(raw[:2000])
        sys.exit(1)


def render_note(digest: dict, display_date: str) -> str:
    lines: list[str] = []

    highlights = digest.get("highlights") or []
    if highlights:
        lines.append("## hottest stuff:")
        for highlight in highlights:
            lines.append(f"- {highlight}")
        lines.append("")
        lines.append("---")
        lines.append("---")

    stories = digest.get("stories") or []
    for story in stories:
        title = story.get("title", "Untitled")
        lines.append(f"### {title}")
        if story.get("summary"):
            lines.append(str(story["summary"]))
            lines.append("")
        if story.get("why_it_matters"):
            lines.append(f"*Why it matters:* {story['why_it_matters']}")
            lines.append("")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    today = datetime.now(ZoneInfo("Europe/Copenhagen"))
    note_date = today.date().isoformat()
    month_folder = f"{today.month}-{today.year:02d}"
    display_date = f"{today.day:02d}/{today.month:02d}-{today.year}"
    file_date = f"{today.day:02d}-{today.month:02d}-{today.year}"
    note_path = os.path.join(month_folder, f"{file_date}.md")

    force_run = os.environ.get("FORCE_RUN", "") == "1"
    if os.path.exists(note_path) and not force_run:
        print(f"{note_path} already exists, nothing to do.")
        sys.exit(0)

    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        print("MISTRAL_API_KEY is not set, exiting with failure.")
        sys.exit(1)

    stories = asyncio.run(fetch_stories())
    if not stories:
        print("No stories found on the front page, nothing to do.")
        sys.exit(0)
    print(f"Fetched {len(stories)} stories.")

    stories = asyncio.run(enrich_with_article_text(stories))
    with_text = sum(1 for s in stories if s.get("article_text"))
    print(f"Enriched {with_text} of {len(stories)} with article text.")

    digest = summarize(api_key, stories, note_date)
    note = render_note(digest, display_date)

    os.makedirs(month_folder, exist_ok=True)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note)
    print(f"Note written: {note_path}")


if __name__ == "__main__":
    main()
