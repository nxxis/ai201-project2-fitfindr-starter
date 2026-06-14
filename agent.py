"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])  # None on success
"""

import re
from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.
    """
    return {
        "query":             query,   # original user query
        "parsed":            {},      # extracted description / size / max_price
        "search_results":    [],      # list of matching listing dicts
        "selected_item":     None,    # top result, passed into suggest_outfit
        "wardrobe":          wardrobe,
        "outfit_suggestion": None,    # string returned by suggest_outfit
        "fit_card":          None,    # string returned by create_fit_card
        "error":             None,    # set if the interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex — no LLM needed.

    Returns:
        dict with keys: description (str), size (str|None), max_price (float|None)
    """
    # Price: "under $30", "less than $40", "max $25", "up to $50"
    price_match = re.search(
        r"(?:under|less than|max|below|no more than|up to)\s*\$?(\d+(?:\.\d+)?)",
        query, re.IGNORECASE
    )
    max_price = float(price_match.group(1)) if price_match else None

    # Size: search on a copy with the price removed so "$30" doesn't match as "30"
    query_no_price = re.sub(r"\$\d+(?:\.\d+)?", "", query)
    size_match = re.search(
        r"\b(XXS|XS|S|M|L|XL|XXL|2XL|3XL|(?:size\s+)?[2-4][0-9]|plus(?:\s+size)?)\b",
        query_no_price, re.IGNORECASE
    )
    size = None
    if size_match:
        raw = re.sub(r"size\s+", "", size_match.group(1), flags=re.IGNORECASE).strip()
        size = raw.upper() if re.match(r"^[a-zA-Z]+$", raw) else raw

    # Description: strip price clause, size clause, and filler phrases
    description = query
    if price_match:
        description = (
            description[:price_match.start()] + description[price_match.end():]
        )
    if size_match:
        description = (
            description[:size_match.start()] + description[size_match.end():]
        )
    for filler in [
        r"i'?m? looking for\b",
        r"i want\b",
        r"find me\b",
        r"can you find\b",
        r"i need\b",
        r"i mostly wear.*",
        r"i (usually|typically) wear.*",
        r"my style is.*",
    ]:
        description = re.sub(filler, "", description, flags=re.IGNORECASE)

    description = description.strip(" .,;")
    if not description:
        description = query[:60]

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request.
        wardrobe: User's wardrobe dict.

    Returns:
        The session dict. Always check session["error"] first —
        if it is not None the interaction ended early and
        outfit_suggestion / fit_card will be None.
    """

    # ── Step 1: initialise session ────────────────────────────────────────────
    session = _new_session(query, wardrobe)

    # ── Step 2: parse the query ───────────────────────────────────────────────
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size        = parsed["size"]
    max_price   = parsed["max_price"]

    print(f"[agent] parsed → description='{description}' size={size} max_price={max_price}")

    # ── Step 3: search_listings ───────────────────────────────────────────────
    results = search_listings(description, size=size, max_price=max_price)
    print(f"[agent] search_listings → {len(results)} result(s)")

    if not results:
        # Build a helpful error message naming exactly what was searched
        parts = [f"'{description}'"]
        if size:
            parts.append(f"size {size}")
        if max_price:
            parts.append(f"under ${max_price:.0f}")
        session["error"] = (
            f"No listings found for {', '.join(parts)}. "
            f"Try a broader description, remove the size filter, "
            f"or raise your price limit."
        )
        return session   # ← stop here, do NOT call suggest_outfit

    # ── Step 4: select top result ─────────────────────────────────────────────
    session["search_results"] = results
    session["selected_item"]  = results[0]
    print(f"[agent] selected → {results[0]['title']} @ ${results[0]['price']}")

    # ── Step 5: suggest_outfit ────────────────────────────────────────────────
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    print(f"[agent] suggest_outfit → {outfit[:80]}...")

    if outfit.startswith("[Error]"):
        session["error"] = outfit
        return session   # ← stop here

    session["outfit_suggestion"] = outfit

    # ── Step 6: create_fit_card ───────────────────────────────────────────────
    fit_card = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    print(f"[agent] create_fit_card → {fit_card}")

    # fit_card failure is non-fatal — store whatever came back
    session["fit_card"] = fit_card

    # ── Step 7: return completed session ─────────────────────────────────────
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Test 1: happy path ===\n")
    s1 = run_agent(
        query="vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if s1["error"]:
        print(f"Error: {s1['error']}")
    else:
        print(f"Found:   {s1['selected_item']['title']}")
        print(f"Outfit:  {s1['outfit_suggestion']}")
        print(f"FitCard: {s1['fit_card']}")

    print("\n=== Test 2: no-results path ===\n")
    s2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"selected_item:     {s2['selected_item']}")
    print(f"outfit_suggestion: {s2['outfit_suggestion']}")
    print(f"fit_card:          {s2['fit_card']}")
    print(f"error:             {s2['error']}")