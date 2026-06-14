# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (`data/listings.json`) for items that match the user's description, optional size, and optional price ceiling. Scores each listing by counting how many keywords from the description appear in the listing's `title`, `description`, `category`, and `style_tags` fields. Hard-filters by `size` (exact, case-insensitive) and `price ≤ max_price` before scoring. Returns results sorted by relevance score, highest first.

**Input parameters:**

- `description` (str): Natural-language keywords describing what the user wants, e.g. `"vintage graphic tee"`. Used for keyword scoring — every word that appears in the listing's text fields adds 1 point to that listing's score.
- `size` (str | None): Clothing size to filter by, e.g. `"M"`, `"S"`, `"28"`. Comparison is case-insensitive. Pass `None` to skip size filtering entirely.
- `max_price` (float | None): Maximum price in USD, inclusive. Pass `None` to skip price filtering entirely.

**What it returns:**
A `list[dict]` of matching listing dicts, sorted by relevance score descending. Each dict has the fields: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str), `platform` (str). Returns an empty list `[]` if no listings match — never raises an exception.

**What happens if it fails or returns nothing:**
If it returns `[]`, the agent sets `session["error"]` to a specific, actionable message such as: *"No listings found for 'vintage graphic tee' in size M under $30. Try broadening your description, removing the size filter, or raising your price limit."* The agent then returns the session immediately — it does NOT proceed to call `suggest_outfit` with empty input. (Stretch: before giving up, the agent retries once without the size filter and once with the price raised 50%.)

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific thrifted item and the user's current wardrobe, calls the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfit combinations. The LLM prompt includes the new item's title, category, style tags, and colors, plus a formatted list of all wardrobe items with their category and style tags. If the wardrobe is empty, the prompt asks for general styling advice — what types of pieces pair well with this item, what aesthetic it fits, and one concrete outfit idea using common basics.

**Input parameters:**

- `new_item` (dict): A single listing dict returned by `search_listings`. Must have at minimum: `title`, `category`, `style_tags`, `colors`, `price`, `platform`. This is what the user is considering buying.
- `wardrobe` (dict): A wardrobe dict following `data/wardrobe_schema.json`. Must have an `"items"` key containing a list of wardrobe item dicts (each with `title`, `category`, `style_tags`, `colors`). The list can be empty — the function handles this gracefully without crashing.

**What it returns:**
A non-empty `str` containing a 2–4 sentence outfit suggestion. For example: *"Pair this faded band tee with your wide-leg jeans and platform Docs for a 90s grunge look. Roll the sleeves once and front-tuck slightly for shape."* If the wardrobe is empty, returns general styling advice instead of wardrobe-specific combos.

**What happens if it fails or returns nothing:**
If the LLM call raises an exception (API error, timeout, missing key), the function catches it and returns the string `"[Error] Could not generate outfit suggestion — please try again."`. This string is checked by the agent; if it starts with `"[Error]"`, the agent sets `session["error"]` and returns early. The function never raises — it always returns a string.

---

### Tool 3: create_fit_card

**What it does:**
Given the outfit suggestion from `suggest_outfit` and the new item's listing details, calls the Groq LLM at high temperature (0.9+) to generate a short, casual, Instagram-style caption for the outfit. The caption should sound like a real person posting an OOTD — lowercase, natural, specific about the item and where it was thrifted. Runs at higher temperature so output varies each time even for the same input.

**Input parameters:**

- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. If empty or whitespace-only, the function returns an error string immediately without calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item (from `search_listings`). Used to pull the item's `title`, `price`, and `platform` to mention in the caption.

**What it returns:**
A `str` of 1–3 sentences suitable as an Instagram caption. For example: *"thrifted this faded nirvana tee off depop for $22 and it was made for my wide-legs 🖤 full look in my stories"*. Returns an error string (starting with `"[Error]"`) if `outfit` is empty or the LLM call fails — never raises an exception.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, returns immediately: `"[Error] No outfit to generate a fit card for."`. If the LLM call fails, returns `"[Error] Could not generate fit card — please try again."`. A fit card error is treated as **non-fatal** by the agent — the agent logs it but does not stop; the session still returns the outfit suggestion.

---

### Additional Tools (if any)

#### Tool 4: compare_price *(Stretch)*

**What it does:**
Finds all other listings in the dataset with the same `category` AND at least one overlapping `style_tag`. Computes their median price using `statistics.median()`. Returns an assessment (deal / fair / overpriced) based on thresholds: ≤80% of median = deal, ≥120% of median = overpriced, otherwise fair.

**Input parameters:**
- `item` (dict): A listing dict with `id`, `category`, `style_tags`, and `price`.

**What it returns:**
A `dict` with keys: `assessment` (str: "deal" | "fair" | "overpriced" | "unknown"), `median_comparable_price` (float | None), `comparable_count` (int), `reasoning` (str — human-readable explanation), `item_price` (float).

**What happens if it fails:**
If fewer than 2 comparable items are found, returns `{"assessment": "unknown", "reasoning": "Not enough comparable listings to evaluate price.", ...}`. Non-blocking — a failure here does not stop the agent.

---

#### Tool 5: check_trends *(Stretch)*

**What it does:**
Calls the Groq LLM with a curated system prompt to surface 5–8 style tags currently trending in secondhand fashion for the given category. Results are injected into the `suggest_outfit` prompt to bias styling toward current trends.

**Input parameters:**
- `category` (str): Clothing category, e.g. `"tops"`.
- `size_range` (str | None): Optional size context.

**What it returns:**
A `dict` with `trending_tags` (list[str]) and `trend_summary` (str). Returns empty tags + error summary on failure.

**What happens if it fails:**
Returns `{"trending_tags": [], "trend_summary": "[Error]..."}`. Non-blocking.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop runs inside `run_agent(query, wardrobe)` and branches on what each tool returns — it does NOT call all three tools unconditionally.

```
1. Parse query → extract description, size, max_price using regex
   - Price: look for "under $X", "less than $X", "max $X"
   - Size: look for M, S, L, XL, XXS, or numeric sizes like 28
   - Description: remainder after removing price/size clauses
   Store in session["parsed"]

2. Call search_listings(description, size, max_price)
   Store results in session["search_results"]

   IF results == [] AND size was set:
     → RETRY: search_listings(description, size=None, max_price)
     → Warn user: "No results for size {size} — broadening to all sizes"
     IF still []:
       → RETRY: search_listings(description, size=None, max_price * 1.5)
       → Warn user: "Still no results — loosening price limit to ${raised}"
       IF still []:
         → set session["error"] = helpful message
         → return session  ← STOP HERE

   IF results == [] (no size was set):
     → set session["error"] = helpful message
     → return session  ← STOP HERE

   IF results found:
     → session["selected_item"] = results[0]

3. Call suggest_outfit(session["selected_item"], wardrobe)
   Store in session["outfit_suggestion"]

   IF result starts with "[Error]":
     → set session["error"] = result
     → return session  ← STOP HERE

4. Call create_fit_card(session["outfit_suggestion"], session["selected_item"])
   Store in session["fit_card"]

   IF result starts with "[Error]":
     → do NOT stop — log the error, leave session["fit_card"] as the error string
     (fit card failure is non-fatal)

5. Return session
```

The critical gate is step 2: `suggest_outfit` is **never** called when `search_listings` returns empty. Step 4 is non-blocking — a fit card failure does not abort the session.

---

## State Management

**How does information from one tool get passed to the next?**

All state is stored in a single `session` dict, initialized once at the start of `run_agent()` via `_new_session()`. Each step writes to the session dict and the next step reads from it:

| Key | Written after | Read by |
|---|---|---|
| `session["parsed"]` | Query parsing | `search_listings` call |
| `session["search_results"]` | `search_listings` | UI display, selecting top item |
| `session["selected_item"]` | Selecting `results[0]` | `suggest_outfit`, `create_fit_card` |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card`, UI panel 2 |
| `session["fit_card"]` | `create_fit_card` | UI panel 3 |
| `session["error"]` | Any failure | UI — stops rendering further panels |

No tool re-queries the user. `session["selected_item"]` that goes into `suggest_outfit` is the **same dict object** that came out of `search_listings` — it is never re-fetched or rebuilt.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool              | Failure mode                          | Agent response |
| ----------------- | ------------------------------------- | -------------- |
| `search_listings`  | No results match the query            | Set `session["error"]` with a specific message naming what was searched and what to try differently. Return session immediately — do not call `suggest_outfit`. (Stretch: retry with loosened constraints first.) |
| `suggest_outfit`   | Wardrobe is empty                     | Do not crash — instead prompt the LLM for general styling advice for the item type. Return a useful string in all cases. |
| `create_fit_card` | Outfit input is missing or incomplete | Return error string `"[Error] No outfit to generate a fit card for."` immediately without calling the LLM. Agent treats this as non-fatal — logs it but continues. |

---

## Architecture

```
User query (natural language)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    run_agent(query, wardrobe)                │
│                                                             │
│  Step 1: Parse query                                        │
│    regex → description, size, max_price                     │
│    → session["parsed"]                                      │
│         │                                                   │
│         ▼                                                   │
│  Step 2: search_listings(description, size, max_price)      │
│    → session["search_results"]                              │
│         │                                                   │
│         ├── results == [] ──────────────────────────────────┤
│         │   [Stretch] retry without size                    │
│         │   [Stretch] retry with raised price               │
│         │   → session["error"] = "No listings found..."    │
│         │   → RETURN session ◄──────────────────────────── │
│         │                                                   │
│         └── results found                                   │
│               session["selected_item"] = results[0]         │
│                     │                                       │
│                     ▼                                       │
│  Step 3: suggest_outfit(selected_item, wardrobe)            │
│    → session["outfit_suggestion"]                           │
│                     │                                       │
│                     ├── starts with "[Error]" ─────────────┤
│                     │   → session["error"]                  │
│                     │   → RETURN session ◄──────────────── │
│                     │                                       │
│                     └── success                             │
│                           │                                 │
│                           ▼                                 │
│  Step 4: create_fit_card(outfit_suggestion, selected_item)  │
│    → session["fit_card"]                                    │
│    (non-fatal — error here does not stop session)           │
│                           │                                 │
│                           ▼                                 │
│  Return completed session                                   │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
app.py / handle_query()
  Panel 1 ← session["selected_item"] (formatted listing text)
  Panel 2 ← session["outfit_suggestion"]
  Panel 3 ← session["fit_card"]
  (if session["error"]: show error in Panel 1, empty Panels 2 & 3)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: I will give Claude the Tool 1 spec block from this file (inputs table, return value, failure mode) and the signature of `load_listings()` from `data_loader.py`. I will ask it to implement the function body using keyword scoring. Before using the output I will verify: (1) it applies size and price filters before scoring, not after; (2) it returns `[]` not `None` on no match; (3) it sorts results by score descending.

For `suggest_outfit`: I will give Claude the Tool 2 spec block plus an example wardrobe dict and example listing dict. I will ask it to build a structured LLM prompt that includes item details and all wardrobe items. I will verify the empty-wardrobe branch exists and returns a non-empty string.

For `create_fit_card`: I will give Claude the Tool 3 spec block and ask it to write a prompt that produces an authentic-sounding Instagram caption. I will verify: (1) the empty-outfit guard exists; (2) temperature is set to 0.9 or higher; (3) running it three times on the same input produces meaningfully different captions.

**Milestone 4 — Planning loop and state management:**

I will give Claude the Architecture diagram above (the ASCII flowchart) plus the Planning Loop and State Management sections. I will ask it to implement `run_agent()` in `agent.py`, following the numbered steps. Before running, I will verify: (1) it branches on `search_results == []` rather than calling all tools unconditionally; (2) it stores values in `session` at each step; (3) `selected_item` flows directly into `suggest_outfit` from the session dict.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query. Regex finds `max_price = 30.0` from "under $30". No explicit size keyword is found (`size = None`). Description is cleaned to `"vintage graphic tee"` by stripping the filler phrase and wardrobe description.

`search_listings("vintage graphic tee", size=None, max_price=30.0)` is called.
The function scores each listing in `listings.json` by counting keyword overlaps ("vintage", "graphic", "tee") in title/description/style_tags. Listings priced over $30 are excluded first.
Returns: `[{"id": "L003", "title": "Faded Band Tee...", "price": 22.0, "platform": "Depop", ...}, ...]` (sorted by score).
`session["search_results"]` = the list. `session["selected_item"]` = `results[0]`.

**Step 2:**
`suggest_outfit(session["selected_item"], wardrobe)` is called with the top listing dict and the user's wardrobe (which has wide-leg jeans, chunky sneakers, a denim jacket, etc.).
The LLM receives a prompt describing the band tee and listing all wardrobe items.
Returns: `"Pair this faded band tee with your wide-leg jeans and platform Docs for a 90s grunge look. Roll the sleeves once and front-tuck slightly for shape."`
`session["outfit_suggestion"]` = that string.

**Step 3:**
`create_fit_card(session["outfit_suggestion"], session["selected_item"])` is called.
The LLM receives the outfit text plus the item's title ($22, Depop) and generates a casual caption at temperature 0.9.
Returns: `"thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤 full look dropping soon"`
`session["fit_card"]` = that string.

**Final output to user:**
- Panel 1 (listing): "Faded Band Tee — $22.00 · Depop · Good · Size M · vintage, grunge, graphic, band tee"
- Panel 2 (outfit): "Pair this faded band tee with your wide-leg jeans and platform Docs for a 90s grunge look. Roll the sleeves once and front-tuck slightly for shape."
- Panel 3 (fit card): "thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤 full look dropping soon"