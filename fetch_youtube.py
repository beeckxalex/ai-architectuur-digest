#!/usr/bin/env python3
"""Weekly YouTube digest for AI-in-architecture.

Reads YOUTUBE_API_KEY from the environment, fetches:
  1. new uploads from a fixed list of channels (cheap: ~1 quota unit per call)
  2. keyword discovery searches for new videos from other channels (100 units per search)
and writes data/youtube-latest.md and data/youtube-latest.json.

Standard library only. Free quota is 10,000 units/day; one run uses well under 1,000.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://www.googleapis.com/youtube/v3"
DAYS_BACK = 8  # a bit over a week so a Sunday run never misses a day

CHANNELS = [
    ("Show It Better", "UC_eRv_Rzr671BaKFtpYSi4A"),
    ("The Architecture Grind", "UCKSC6fPmd1SrPaWhOkJAkmg"),
    ("ArchiTech Network", "UCrLHBCOz211YirQRg2QVJvA"),
    ("altArch", "UCP9th7OxCWj2dAkLimSwKgA"),
    ("Melos Azemi", "UC3olXC49iDxPeHq2HE3GrGg"),
    ("Urban Decoders", "UCnO6YjOE3-CIm0x5Z2easzw"),
    ("renderdrop", "UCG1bQ55II0VREN6Y3-XiOjg"),
    ("Danny Loza (aiforarchitect)", "UCJmesF6SX4RTul3YrZuY2Dg"),
    ("Nuno Silva", "UC16Hy0D3KBn9xeMyL7jQAjw"),
    # Add more as (name, channel_id). Vendor channels (Chaos, Graphisoft,
    # Autodesk, Vectorworks, Archi Hacks) can be added here once you have their IDs.
]

SEARCH_QUERIES = [
    "AI architecture workflow",
    "Veras Enscape AI render",
    "Midjourney architecture",
    "ChatGPT for architects",
    "Archicad AI",
    "Revit AI",
]


def api_get(endpoint, params, key):
    params = dict(params, key=key)
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"HTTP {e.code} on {endpoint}: {body}", file=sys.stderr)
    except Exception as e:  # network errors etc.
        print(f"Error on {endpoint}: {e}", file=sys.stderr)
    return None


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def channel_uploads(name, channel_id, since, key):
    """Return video ids uploaded since `since` (uploads playlist = UU + id[2:])."""
    playlist = "UU" + channel_id[2:]
    data = api_get(
        "playlistItems",
        {"part": "contentDetails", "playlistId": playlist, "maxResults": 15},
        key,
    )
    ids = []
    if not data:
        return ids
    for item in data.get("items", []):
        cd = item.get("contentDetails", {})
        published = cd.get("videoPublishedAt")
        if published and parse_time(published) >= since:
            ids.append(cd["videoId"])
    return ids


def search_videos(query, since, key):
    data = api_get(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxResults": 8,
            "relevanceLanguage": "en",
        },
        key,
    )
    if not data:
        return []
    return [i["id"]["videoId"] for i in data.get("items", []) if "videoId" in i.get("id", {})]


def video_details(ids, key):
    out = {}
    ids = list(dict.fromkeys(ids))  # dedupe, keep order
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        data = api_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
            key,
        )
        if not data:
            continue
        for v in data.get("items", []):
            sn, st = v.get("snippet", {}), v.get("statistics", {})
            out[v["id"]] = {
                "id": v["id"],
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "title": sn.get("title", ""),
                "channel": sn.get("channelTitle", ""),
                "published": sn.get("publishedAt", ""),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
                "duration": v.get("contentDetails", {}).get("duration", ""),
                "description": (sn.get("description", "") or "")[:300].replace("\n", " "),
            }
    return out


def fmt_line(v):
    date = v["published"][:10]
    return (
        f"- **{v['title']}** ({v['channel']}, {date}) - {v['views']:,} views, "
        f"{v['likes']:,} likes, {v['comments']:,} comments\n  {v['url']}\n"
        + (f"  {v['description']}\n" if v["description"] else "")
    )


def main():
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        sys.exit("YOUTUBE_API_KEY is not set")

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS_BACK)

    channel_ids = {}
    for name, cid in CHANNELS:
        channel_ids[name] = channel_uploads(name, cid, since, key)
    search_ids = {q: search_videos(q, since, key) for q in SEARCH_QUERIES}

    all_ids = [i for ids in channel_ids.values() for i in ids]
    all_ids += [i for ids in search_ids.values() for i in ids]
    details = video_details(all_ids, key)

    followed = {}
    for name, ids in channel_ids.items():
        vids = sorted((details[i] for i in ids if i in details), key=lambda v: -v["views"])
        followed[name] = vids

    seen = {v["id"] for vids in followed.values() for v in vids}
    discovery = {}
    for q, ids in search_ids.items():
        vids = [details[i] for i in ids if i in details and i not in seen]
        for v in vids:
            seen.add(v["id"])
        discovery[q] = vids

    lines = [
        "# YouTube digest: AI in architecture",
        f"Generated {now:%Y-%m-%d %H:%M} UTC. Covers uploads since {since:%Y-%m-%d}.",
        "Numbers come from the YouTube Data API at generation time.",
        "",
        "## New videos from followed channels",
    ]
    any_followed = False
    for name, vids in followed.items():
        if vids:
            any_followed = True
            lines.append(f"\n### {name}")
            lines += [fmt_line(v) for v in vids]
    if not any_followed:
        lines.append("\nNo new videos from followed channels in this period.")

    lines.append("\n## Discovery: most-viewed new videos per search")
    any_disc = False
    for q, vids in discovery.items():
        if vids:
            any_disc = True
            lines.append(f"\n### Search: {q}")
            lines += [fmt_line(v) for v in vids]
    if not any_disc:
        lines.append("\nNo discovery results in this period.")

    os.makedirs("data", exist_ok=True)
    with open("data/youtube-latest.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open("data/youtube-latest.json", "w", encoding="utf-8") as f:
        json.dump(
            {"generated": now.isoformat(), "since": since.isoformat(),
             "followed": followed, "discovery": discovery},
            f, ensure_ascii=False, indent=2,
        )
    print(f"Wrote digest: {sum(len(v) for v in followed.values())} followed, "
          f"{sum(len(v) for v in discovery.values())} discovery videos.")


if __name__ == "__main__":
    main()
