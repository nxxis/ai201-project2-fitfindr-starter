"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price) → list[dict]
    suggest_outfit(new_item, wardrobe) → str
    create_fit_card(outfit, new_item) → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
            (e.g., "vintage graphic tee").
        size: Size string to filter by, or None to skip size filtering.
            Matching is case-insensitive (e.g., "M" matches "m").
        max_price: Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
        Each listing dict has the following fields:
            id, title, description, category, style_tags (list), size,
            condition, price (float), colors (list), brand, platform
    """
    # Step 1: Load all listings — return [] if file can't be read
    try:
        listings = load_listings()
    except Exception as e:
        print(f"[search_listings] Error loading listings: {e}")
        return []

    # Step 2: Tokenise the description into lowercase keywords
    keywords = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", description)]

    scored = []
    for item in listings:

        # Hard filter — price
        if max_price is not None and item.get("price", 0) > max_price:
            continue

        # Hard filter — size (case-insensitive exact match)
        if size is not None:
            if item.get("size", "").lower() != size.lower():
                continue

        # Score by keyword overlap across text fields
        searchable = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            " ".join(item.get("style_tags", [])),
            " ".join(item.get("colors", [])),
            item.get("brand") or "",
        ]).lower()

        score = sum(1 for kw in keywords if kw in searchable)

        # Drop listings with zero overlap
        if score > 0:
            scored.append((score, item))

    # Sort by score descending and return just the dicts
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1-2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
            wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
        Returns an error string starting with "[Error]" if the LLM call fails.
    """
    # Guard: must receive a valid item dict
    if not isinstance(new_item, dict) or not new_item:
        return "[Error] No valid item provided to suggest_outfit."

    wardrobe_items = wardrobe.get("items", [])

    # Format new item details for the prompt
    item_detail = (
        f"Title: {new_item.get('title', 'Unknown')}\n"
        f"Category: {new_item.get('category', 'Unknown')}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Condition: {new_item.get('condition', 'Unknown')}\n"
        f"Price: ${new_item.get('price', 0):.2f} from {new_item.get('platform', 'unknown')}"
    )

    # Branch on empty vs populated wardrobe
    if not wardrobe_items:
        user_prompt = (
            f"I just thrifted this item:\n{item_detail}\n\n"
            f"My wardrobe is pretty bare right now. Give me general styling advice "
            f"for this piece: what kind of basics would pair well with it, what aesthetic "
            f"it fits, and one specific outfit idea using everyday wardrobe staples."
        )
    else:
        wardrobe_lines = []
        for w in wardrobe_items:
            tags = ", ".join(w.get("style_tags", []))
            colors = ", ".join(w.get("colors", []))
            wardrobe_lines.append(
                f"- {w.get('title', 'Item')} ({w.get('category', '')}): "
                f"{tags} | colors: {colors}"
            )
        wardrobe_str = "\n".join(wardrobe_lines)

        style_prefs = wardrobe.get("style_preferences", [])
        prefs_str = ", ".join(style_prefs) if style_prefs else "not specified"

        user_prompt = (
            f"I just thrifted this item:\n{item_detail}\n\n"
            f"My current wardrobe includes:\n{wardrobe_str}\n\n"
            f"My general style preferences: {prefs_str}\n\n"
            f"Suggest 1-2 specific outfit combinations using pieces from my wardrobe. "
            f"Name the exact wardrobe pieces. Keep it conversational and practical — "
            f"2 to 4 sentences, no bullet points."
        )

    system_prompt = (
        "You are a knowledgeable personal stylist who specialises in thrifted and "
        "secondhand fashion. Give practical, specific outfit suggestions that reflect "
        "a real personal style. Be conversational — no lists, no headers, just natural "
        "styling advice in 2-4 sentences."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except ValueError as e:
        return f"[Error] {e}"
    except Exception as e:
        return f"[Error] Could not generate outfit suggestion — please try again. ({e})"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit: The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 1-3 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    # Guard: empty or whitespace-only outfit string
    if not outfit or not outfit.strip():
        return "[Error] No outfit to generate a fit card for — make sure suggest_outfit ran successfully."

    # Guard: missing or invalid item dict
    if not isinstance(new_item, dict) or not new_item:
        return "[Error] No item data provided to create_fit_card."

    title    = new_item.get("title", "this thrifted find")
    platform = new_item.get("platform", "a thrift store")
    price    = new_item.get("price", 0)
    price_str = f"${price:.0f}" if price else "a steal"

    user_prompt = (
        f"I thrifted: {title} from {platform} for {price_str}.\n"
        f"Here's the outfit I put together: {outfit}\n\n"
        f"Write a casual Instagram caption for this outfit. Rules:\n"
        f"- 1 to 2 sentences maximum\n"
        f"- All lowercase\n"
        f"- Sound like a real person, not a brand\n"
        f"- Mention the item and where it's from naturally\n"
        f"- No hashtags\n"
        f"- You may use 1-2 emojis if they feel right"
    )

    system_prompt = (
        "You write casual, authentic Instagram captions for thrift haul posts. "
        "Write in lowercase. Maximum 2 sentences. Sound like a real person sharing "
        "a fit they're genuinely excited about — not a brand, not a stylist."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.95,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except ValueError as e:
        return f"[Error] {e}"
    except Exception as e:
        return f"[Error] Could not generate fit card — please try again. ({e})"