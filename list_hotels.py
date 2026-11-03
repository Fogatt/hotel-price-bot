"""List every hotel LiteAPI has for the first search area in config.json,
with its ID, so you can pick names or IDs for "hotel_names" / "hotel_ids".

Run:  LITEAPI_KEY=sand_... python list_hotels.py
"""

import json
import os

import bot

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")) as f:
    search = json.load(f)["searches"][0]

hotels = bot.area_hotels(search, os.environ["LITEAPI_KEY"])
print(f"{len(hotels)} hotels near '{search['name']}':")
for hid, h in sorted(hotels.items(), key=lambda kv: kv[1].get("name", "")):
    print(f"{hid:<12} {h.get('name')}")
