#!/usr/bin/env python3
"""Weekly Reddit digest for AI-in-architecture via the Apify actor practicaltools/apify-reddit-api."""
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
MAX_ITEMS = 25
SUBREDDITS = ["Architects", "archviz", "Revit", "ArchiCAD"]

AI_WORDS = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|chatgpt|gpt|claude|gemini|copilot|llm|"
    r"midjourney|stable diffusion|comfyui|veras|enscape|d5|generative|machine learning|"
    r"automation|automate|script|dynamo|grasshopper|plugin|agent|mcp)\b",
    re.I,
)


def build_payload():
    payload = {}
    payload["startUrls"] = [{"url": f"https://www.reddit.com/r/{s}/"} for s in SUBREDDITS]
    payload["maxItems"] = MAX_ITEMS * len(SUBREDDITS)
    payload["searches"] = []
    payload["searchPosts"] = False
    payload["searchComments"] = False
    payload["searchCommunities"] = False
    payload["searchUsers"] = False
    payload["ignorestartUrls"] = False
    payload["fetchPostComments"] = False
    payload["skipComments"] = True
    payload["skipCommunity"] = True
    payload["skipUserPosts"] = True
    payload["includeNSFW"] = False
    payload["sort"] = "top"
    payload["time"] = "week"
    return payload


def run_actor(token):
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(build_payload()).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit("Apify HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))


def main():
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS_BACK)
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("APIFY_TOKEN is not set")
    items = run_actor(token)
    for it in items[:5]:
        print("DEBUG", it.get("dataType"), it.get("communityName"), it.get("parsedCommunityName"), it.get("createdAt"), (it.get("title") or "")[:60])

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
        body = it.get("body", "") or ""
        text = (it.get("title", "") or "") + " " + body
        excerpt = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", body)).strip()[:300]
        posts.append({
            "subreddit": sub,
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "upvotes": it.get("upVotes", 0),
            "comments": it.get("numberOfComments", 0),
            "created": created[:10],
            "ai_related": bool(AI_WORDS.search(text)),
            "excerpt": excerpt,
        })

    posts.sort(key=lambda p: -(p["upvotes"] or 0))
    ai = [p for p in posts if p["ai_related"]]
    other = [p for p in posts if not p["ai_related"]][:5]

    def fmt(p):
        line = "- **%s** (r/%s, %s) - %s upvotes, %s comments\n  %s\n" % (
            p["title"], p["subreddit"], p["created"], p["upvotes"], p["comments"], p["url"])
        if p["excerpt"]:
            line += "  " + p["excerpt"] + "\n"
        return line

    lines = ["# Reddit digest: AI in architecture"]
    lines.append("Generated %s UTC. Top posts of the week from %s." % (
        now.strftime("%Y-%m-%d %H:%M"), ", ".join("r/" + s for s in SUBREDDITS)))
    lines.append("")
    lines.append("## AI-related posts (by upvotes)")
    lines += [fmt(p) for p in ai] or ["", "No AI-related posts found this week."]
    lines.append("")
    lines.append("## Other top posts (context)")
    lines += [fmt(p) for p in other] or ["", "None."]

    os.makedirs("data", exist_ok=True)
    with open("data/reddit-latest.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open("data/reddit-latest.json", "w", encoding="utf-8") as f:
        json.dump({"generated": now.isoformat(), "posts": posts}, f, ensure_ascii=False, indent=2)
    print("Wrote %d AI-related and %d other posts (%d items fetched)." % (len(ai), len(other), len(items)))


if __name__ == "__main__":
    main()
