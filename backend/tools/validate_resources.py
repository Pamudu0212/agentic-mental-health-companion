#!/usr/bin/env python3
import json, os, requests, sys

# Path to your resources.json (adjusted for app/data)
RESOURCE_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "data", "resources.json")
)

REQUIRED_FIELDS = ["id", "type", "title", "url", "moods", "keywords", "why", "source"]

def validate() -> int:
    print(f"Using: {RESOURCE_FILE}")
    if not os.path.exists(RESOURCE_FILE):
        print("ERROR: resources.json not found at that path.")
        return 1

    with open(RESOURCE_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print("ERROR: Could not parse JSON:", e)
            return 1

    if not isinstance(data, list):
        print("ERROR: Expected a JSON list at the root (e.g., [ {...}, {...} ])")
        return 1

    seen_ids = set()
    errors, warnings = [], []

    for i, item in enumerate(data, 1):
        # Required fields
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                errors.append(f"Item {i} ({item.get('id')}) missing field: {field}")

        # Duplicate IDs
        rid = item.get("id")
        if rid:
            if rid in seen_ids:
                errors.append(f"Duplicate id: {rid}")
            seen_ids.add(rid)

        # URL format
        url = item.get("url", "")
        if url and not (url.startswith("http://") or url.startswith("https://")):
            errors.append(f"Invalid URL format in {rid}: {url}")

        # Lightweight reachability (optional)
        if url.startswith("http"):
            try:
                r = requests.head(url, timeout=5, allow_redirects=True)
                if r.status_code >= 400:
                    warnings.append(f"⚠️  URL may be unreachable ({r.status_code}) in {rid}: {url}")
            except Exception:
                warnings.append(f"⚠️  Could not check URL for {rid}: {url}")

    print("\n=== Validation Report ===")
    if errors:
        print("Errors:")
        for e in errors:
            print(" -", e)
    else:
        print("No blocking errors ✅")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(" -", w)
    else:
        print("No warnings 🚀")

    print(f"\nSummary: {len(data)} resources · {len(errors)} errors · {len(warnings)} warnings")
    return 0 if not errors else 2

if __name__ == "__main__":
    sys.exit(validate())
