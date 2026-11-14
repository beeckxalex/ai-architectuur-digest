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
