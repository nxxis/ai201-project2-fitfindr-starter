# FitFindr 👗

An AI-powered multi-tool agent for finding secondhand pieces and building outfits around them.

FitFindr takes a natural-language query, searches a dataset of secondhand listings, suggests a complete outfit using your wardrobe, and generates a shareable fit card — handling every failure gracefully along the way.

---

## Setup

```bash
git clone https://github.com/YOUR-USERNAME/ai201-project2-fitfindr-starter
cd ai201-project2-fitfindr-starter

python -m venv .venv

# Mac/Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
pip install pytest
```

Create a `.env` file in the repo root:

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
# Open http://127.0.0.1:7860
```

Run tests:

```bash
python -m pytest tests/ -v
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| Parameter     | Type            | Purpose                                                  |
| ------------- | --------------- | -------------------------------------------------------- |
| `description` | `str`           | Natural-language keywords, e.g. `"vintage graphic tee"`  |
| `size`        | `str \| None`   | Exact size filter, case-insensitive. `None` = no filter. |
| `max_price`   | `float \| None` | Maximum price in USD inclusive. `None` = no filter.      |

**Returns:** `list[dict]` — matching listings sorted by relevance score. Each dict contains `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` on no match — never raises.

**How it works:** Applies hard price and size filters first, then scores each remaining listing by counting how many keywords from `description` appear across `title`, `description`, `category`, `style_tags`, `colors`, and `brand`. Results sorted by score descending.

---

### `suggest_outfit(new_item, wardrobe)`

| Parameter  | Type   | Purpose                                           |
| ---------- | ------ | ------------------------------------------------- |
| `new_item` | `dict` | A listing dict from `search_listings`             |
| `wardrobe` | `dict` | User wardrobe with an `items` list (can be empty) |

**Returns:** `str` — 2–4 sentence outfit suggestion. If wardrobe is empty, returns general styling advice instead of wardrobe-specific combos. Returns `[Error]` string on LLM failure — never raises.

---

### `create_fit_card(outfit, new_item)`

| Parameter  | Type   | Purpose                                               |
| ---------- | ------ | ----------------------------------------------------- |
| `outfit`   | `str`  | Outfit suggestion from `suggest_outfit`               |
| `new_item` | `dict` | The listing dict (for title, price, platform context) |

**Returns:** `str` — 1–2 sentence casual Instagram-style caption. Runs at temperature 0.95 so output varies each call. Returns `[Error]` string if `outfit` is empty or LLM fails — never raises.

---

## How the Planning Loop Works

The loop runs inside `run_agent()` in `agent.py`. It branches based on what each tool returns — it does **not** call all three tools unconditionally.

```
1. Parse query → extract description, size, max_price via regex

2. search_listings(description, size, max_price)
   ├── results == []  →  set session["error"], RETURN EARLY
   └── results found  →  session["selected_item"] = results[0]

3. suggest_outfit(selected_item, wardrobe)
   ├── starts with "[Error]"  →  set session["error"], RETURN EARLY
   └── success  →  session["outfit_suggestion"] = result

4. create_fit_card(outfit_suggestion, selected_item)
   └── result stored regardless (failure here is non-fatal)

5. Return session
```

The critical gate is step 2: `suggest_outfit` is **never called** when `search_listings` returns empty. This was verified in both the CLI tests and the live UI.

---

## State Management

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call:

| Key                            | Set after              | Read by                             |
| ------------------------------ | ---------------------- | ----------------------------------- |
| `session["parsed"]`            | Query parsing          | `search_listings` call              |
| `session["search_results"]`    | `search_listings`      | UI panel 1                          |
| `session["selected_item"]`     | Selecting `results[0]` | `suggest_outfit`, `create_fit_card` |
| `session["outfit_suggestion"]` | `suggest_outfit`       | `create_fit_card`, UI panel 2       |
| `session["fit_card"]`          | `create_fit_card`      | UI panel 3                          |
| `session["error"]`             | Any failure            | UI — stops further panels rendering |

No tool re-queries the user or re-fetches data. The `selected_item` passed to `suggest_outfit` is the **identical dict object** that came out of `search_listings`.

---

## Error Handling Strategy

| Tool              | Failure mode          | Agent response                                                                                                                                                |
| ----------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `search_listings` | Returns `[]`          | Sets `session["error"]` with a specific message naming what was searched and what to try differently. Returns immediately — `suggest_outfit` is never called. |
| `suggest_outfit`  | Empty wardrobe        | Does not crash — LLM is prompted for general styling advice instead of wardrobe-specific combos. Always returns a non-empty string.                           |
| `suggest_outfit`  | LLM API error         | Returns `"[Error] Could not generate outfit suggestion..."`. Agent sets `session["error"]` and returns early.                                                 |
| `create_fit_card` | Empty `outfit` string | Returns `"[Error] No outfit to generate a fit card for..."` immediately, no LLM call made. Treated as non-fatal by agent.                                     |
| `create_fit_card` | LLM API error         | Returns `"[Error] Could not generate fit card — please try again."` Non-fatal.                                                                                |

**Concrete example from Milestone 5 testing:**

```bash
python -c "from tools import create_fit_card, search_listings; \
results = search_listings('vintage tee', size=None, max_price=50); \
print(create_fit_card('', results[0]))"

# Output:
# [Error] No outfit to generate a fit card for — make sure suggest_outfit ran successfully.
```

---

## AI Usage

### Instance 1: Implementing `search_listings`

I gave Claude the Tool 1 spec from `planning.md` — the inputs table, return value description, and failure mode — along with the `load_listings()` signature. The generated code correctly used keyword scoring but originally called `.get("brand", "")` which crashed on listings where `brand` is `null` in the JSON (becomes `None` in Python). I fixed it to `item.get("brand") or ""` to safely handle null values.

### Instance 2: Implementing the planning loop

I gave Claude the full ASCII architecture diagram from `planning.md` plus the Planning Loop section. The generated `run_agent()` had the correct branching structure. However, the query parser was searching for size in the original query string, which meant the number in `"under $30"` was sometimes extracted as a size. I fixed it by running the size regex on a price-scrubbed copy of the query instead.

---

## Spec Reflection

**One way the spec helped:** Writing the exact conditional logic in `planning.md` before coding meant the planning loop's error branches were correct on the first pass. Specifying that `suggest_outfit` must never be called with empty input made it obvious exactly where the early return needed to go.

**One way implementation diverged:** The spec described the query parser as straightforward regex extraction. In practice, the real listings dataset has `brand: null` on many items, which our spec didn't anticipate. The implementation needed an extra guard (`or ""`) that wasn't in the original design. This was a data quality issue the spec couldn't have predicted without inspecting the actual dataset more carefully first.
