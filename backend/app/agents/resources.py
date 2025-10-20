import json, os
from typing import List, Dict

Resource = Dict[str, str]

# Point to ../data/resources.json (relative to this file)
here = os.path.dirname(__file__)
json_path = os.path.join(here, "..", "data", "resources.json")
json_path = os.path.abspath(json_path)

with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Since resources.json is just a list
CATALOG: List[Resource] = data

# Synonyms for matching
SYNONYMS = {
    "exam": ["test", "midterm", "finals", "assignment", "schoolwork"],
    "sleep": ["insomnia", "tired", "can't sleep", "night"],
    "sadness": ["lonely", "down", "blue", "tearful", "depressed"],
    "stress": ["burnout", "overload", "pressure"],
    "anxiety": ["panic", "fear", "worry", "nervous"],
}
