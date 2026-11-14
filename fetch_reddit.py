#!/usr/bin/env python3
"""Weekly Reddit digest for AI-in-architecture, via the Apify actor
practicaltools/apify-reddit-api. Reads APIFY_TOKEN from the environment and
writes data/reddit-latest.md and data/reddit-latest.json. Standard library only.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ACTOR = "practicaltools~apify-reddit-api"
ENDPOINT = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
DAYS_BACK = 8
MAX_ITEMS = 25  # per start URL; keep low to stay inside the free 1,000 results/month
SUBREDDITS = ["Architects", "archviz", "Revit", "ArchiCAD"]

AI_WORDS = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|chatgpt|gpt|claude|gemini|copilot|llm|"
    r"midjourney|stable diffusion|comfyui|veras|enscape|d5|generative|machine learning|"
    r"automation|automate|script|dynamo|grasshopper|plugin|agent|mcp|render(?:ing)? ai)\b",
    re.I,
)


def run_actor(token):
    payload = {
        "startUrls": [{"url": f"https://www.reddit.com/r/{s}/top/?t=week"} for s in SUBREDDITS],
        "maxItems": MAX_ITEMS * len(SUBREDDITS),
        "searches": [],
        "searchPosts": False,
        "searchComments": False,
        "searchCommunities": False,
        "searchUsers": False,
        "ignorestartUrls": False,
        "fetchPostComments": False,
        "skipComments": True,
        "skipCommunity": True,
        "skipUserPosts": True,
        "includeNSFW": False,
        "sort": "top",
        "time": "week",
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Apify HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def main():
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS_BACK)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("APIFY_TOKEN is not set")
    items = run_actor(token)

    wanted = {s.lower() for s in SUBREDDITS}
    posts = []
    for it in items:
        if it.get("dataType") != "post" or it.get("isAd"):
            continue
        sub = (it.get("parsedCommunityName") or it.get("communityName") or "").replace("r/", "")
        if sub.lower() not in wanted:
            continue
        created = it.get("createdAt", "")
        try:
            if datetime.fromisoformat(created.replace("Z", "+00:00")) < since:
                continue
        except ValueError:
            pass
        text = f"{it.get('title', '')} {it.get('body', '')}"
        posts.append({
            "subreddit": sub,
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "upvotes": it.get("upVotes", 0),
            "comments": it.get("numberOfComments", 0),
            "created": created[:10],
            "ai_related": bool(AI_WORDS.search(text)),
            "excerpt": re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", it.get("body", "") or "")).strip()[:300],
        })

    posts.sort(key=lambda p: -(p["upvotes"] or 0))
    ai = [p for p in posts if p["ai_related"]]
    other = [p for p in posts if not p["ai_related"]][:5]

    def fmt(p):
        return (f"- **{p['title']}** (r/{p['subreddit']}, {p['created']}) - "
                f"{p['upvotes']} upvotes, {p['comments']} comments\n  {p['url']}\n"
                + (f"  {p['excerpt']}\n" if p["excerpt"] else ""))

    lines = [
        "# Reddit digest: AI in architecture",
        f"Generated {now:%Y-%m-%d %H:%M} UTC. Top posts of the week from "
        + ", ".join(f"r/{s}" for s in SUBREDDITS) + ".",
        "",
        "## AI-related posts (by upvotes)",
    ]
    lines += [fmt(p) for p in ai] or ["\nNo AI-related posts found this week."]
    lines += ["", "## Other top posts (context)"]
    lines += [fmt(p) for p in other] or ["\nNone."]

    os.makedirs("data", exist_ok=True)
    with open("data/reddit-latest.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open("data/reddit-latest.json", "w", encoding="utf-8") as f:
        json.dump({"generated": now.isoformat(), "posts": posts}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(ai)} AI-related and {len(other)} other posts ({len(items)} items fetched).")


if __name__ == "__main__":
    main()
