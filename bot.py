"""Hourly hotel price checker: LiteAPI -> Telegram.

Reads searches from config.json, finds hotels whose cheapest available
price per night is at or below max_price_per_night, and sends the list
to a Telegram chat. Uses only the Python standard library.

Environment variables:
  LITEAPI_KEY         LiteAPI key (sand_... for sandbox, prod_... for live)
  TELEGRAM_BOT_TOKEN  token from @BotFather
  TELEGRAM_CHAT_ID    your chat id (see get_chat_id.py)
  DRY_RUN=1           print the message instead of sending it
"""

import datetime as dt
import html
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.liteapi.travel/v3.0"
TG_LIMIT = 4000  # Telegram max is 4096 chars per message


def http(method, url, headers=None, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {detail}") from None


def lite(method, path, key, params=None, body=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return http(method, url, {"X-API-Key": key, "Accept": "application/json"}, body)


def normalize(text):
    """Lowercase and strip accents so 'Pousada Zé' matches 'pousada ze'."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def name_matches(wanted, hotel_name):
    """True if every word of `wanted` appears in the hotel name."""
    words = re.findall(r"\w+", normalize(wanted))
    name = normalize(hotel_name)
    return bool(words) and all(w in name for w in words)


def hotels_by_id(ids, key):
    """Look up names for an explicit list of hotel IDs."""
    hotels = {}
    for hid in ids:
        try:
            info = lite("GET", "/data/hotel", key, params={"hotelId": hid}).get("data") or {}
        except RuntimeError as exc:
            print(f"Could not look up {hid}: {exc}", file=sys.stderr)
            info = {}
        hotels[hid] = {"id": hid, "name": info.get("name", hid), "stars": info.get("starRating") or info.get("stars")}
    return hotels


def find_hotels(search, key):
    """Return {hotelId: hotel_info} for the search.

    - "hotel_ids": check exactly these LiteAPI hotel IDs (no area needed).
    - "hotel_names": search the area, keep only hotels whose name contains
      one of these words (case and accents ignored).
    - neither: every hotel in the area.
    """
    if search.get("hotel_ids"):
        return hotels_by_id(search["hotel_ids"], key)
    hotels = area_hotels(search, key)
    wanted = [n for n in search.get("hotel_names", []) if str(n).strip()]
    if wanted:
        kept, unmatched = {}, []
        for w in wanted:
            hits = {hid: h for hid, h in hotels.items() if name_matches(w, h.get("name", ""))}
            if not hits:
                unmatched.append(w)
            else:
                names = "; ".join(sorted(h.get("name", hid) for hid, h in hits.items()))
                print(f"'{search['name']}': name '{w}' matched {len(hits)} hotel(s): {names}")
            kept.update(hits)
        for w in unmatched:
            print(f"'{search['name']}': no hotel in the area matches name '{w}'", file=sys.stderr)
        hotels = kept
    return hotels


def area_hotels(search, key):
    params = {"limit": 1000}
    if "latitude" in search:
        params.update(
            latitude=search["latitude"],
            longitude=search["longitude"],
            radius=search.get("radius_meters", 10000),
        )
    else:
        params.update(countryCode=search["country_code"], cityName=search["city_name"])
    res = lite("GET", "/data/hotels", key, params=params)
    return {h["id"]: h for h in res.get("data", []) if h.get("id")}


def cheapest_total(hotel_rates):
    """Cheapest total stay price (amount, currency) from one /hotels/rates entry."""
    best = None
    for room in hotel_rates.get("roomTypes", []):
        candidates = []
        offer = room.get("offerRetailRate") or {}
        if offer.get("amount") is not None:
            candidates.append((offer["amount"], offer.get("currency")))
        for rate in room.get("rates", []):
            for t in (rate.get("retailRate") or {}).get("total", []):
                if t.get("amount") is not None:
                    candidates.append((t["amount"], t.get("currency")))
        for amount, cur in candidates:
            amount = float(amount)
            if best is None or amount < best[0]:
                best = (amount, cur)
    return best


def get_rates(search, hotel_ids, key):
    results = []
    for i in range(0, len(hotel_ids), 200):  # batch to keep requests reasonable
        body = {
            "hotelIds": hotel_ids[i : i + 200],
            "checkin": search["checkin"],
            "checkout": search["checkout"],
            "currency": search.get("currency", "USD"),
            "guestNationality": search.get("guest_nationality", "US"),
            "occupancies": [{"adults": search.get("adults", 2)}],
            "timeout": 20,
        }
        res = lite("POST", "/hotels/rates", key, body=body)
        results.extend(res.get("data", []) or [])
    return results


def run_search(search, key):
    nights = (dt.date.fromisoformat(search["checkout"]) - dt.date.fromisoformat(search["checkin"])).days
    if nights <= 0:
        raise ValueError(f"{search['name']}: checkout must be after checkin")
    hotels = find_hotels(search, key)
    if not hotels:
        return nights, len(hotels), []
    matches = []
    max_price = search.get("max_price_per_night")
    priced = set()
    for entry in get_rates(search, list(hotels), key):
        best = cheapest_total(entry)
        if not best:
            continue
        total, cur = best
        per_night = total / nights
        info = hotels.get(entry.get("hotelId"), {})
        priced.add(entry.get("hotelId"))
        print(f"   {info.get('name', entry.get('hotelId'))}: {money(per_night, cur or '')}/night")
        if max_price is None or per_night <= float(max_price):
            matches.append(
                {
                    "name": info.get("name", entry.get("hotelId")),
                    "stars": info.get("stars"),
                    "per_night": per_night,
                    "total": total,
                    "currency": cur or search.get("currency", "USD"),
                }
            )
    for hid, h in hotels.items():
        if hid not in priced:
            print(f"   {h.get('name', hid)}: no rooms/price for these dates")
    matches.sort(key=lambda m: m["per_night"])
    return nights, len(hotels), matches


def money(v, cur):
    return f"{cur} {v:,.2f}"


def format_message(search, nights, hotel_count, matches):
    e = html.escape
    lines = [
        f"🏨 <b>{e(search['name'])}</b>",
        f"{search['checkin']} → {search['checkout']} ({nights} nights), {search.get('adults', 2)} adults",
        (
            f"Max: {money(float(search['max_price_per_night']), search.get('currency', 'USD'))}/night"
            if search.get("max_price_per_night") is not None
            else "No max price set: showing all prices"
        ),
        f"{len(matches)} of {hotel_count} hotels match:",
        "",
    ]
    for m in matches:
        stars = f" {'★' * int(m['stars'])}" if m.get("stars") else ""
        lines.append(
            f"• <b>{e(str(m['name']))}</b>{stars}\n"
            f"   {money(m['per_night'], m['currency'])}/night · total {money(m['total'], m['currency'])}"
        )
    return "\n".join(lines)


def split_message(text):
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > TG_LIMIT:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks


def send_telegram(text):
    if os.environ.get("DRY_RUN") == "1":
        print("---- message ----\n" + text)
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for chunk in split_message(text):
        http(
            "POST",
            f"https://api.telegram.org/bot{token}/sendMessage",
            body={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True},
        )


def main():
    key = os.environ.get("LITEAPI_KEY")
    if not key:
        sys.exit("LITEAPI_KEY is not set")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")) as f:
        text = f.read()
    try:
        config = json.loads(text)
    except json.JSONDecodeError as exc:
        bad_line = text.splitlines()[exc.lineno - 1] if exc.lineno <= len(text.splitlines()) else ""
        msg = (
            f"config.json is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg}).\n"
            f"Line {exc.lineno}: {bad_line.strip()}\n"
            'Tip: text must be in double quotes, e.g. ["ze maria"], and items are separated by commas.'
        )
        print("ERROR: " + msg, file=sys.stderr)
        if os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("DRY_RUN") == "1":
            send_telegram("⚠️ Hotel bot: " + html.escape(msg))
        sys.exit(1)

    failed = False
    today = dt.date.today()
    for search in config["searches"]:
        if dt.date.fromisoformat(search["checkin"]) < today:
            print(f"Skipping '{search['name']}': check-in date has passed")
            continue
        try:
            nights, count, matches = run_search(search, key)
        except Exception as exc:  # report and keep going with other searches
            failed = True
            print(f"ERROR in '{search['name']}': {exc}", file=sys.stderr)
            send_telegram(f"⚠️ Hotel bot error in <b>{html.escape(search['name'])}</b>:\n{html.escape(str(exc))}")
            continue
        print(f"'{search['name']}': {count} hotels found, {len(matches)} at or below max price")
        if matches:
            send_telegram(format_message(search, nights, count, matches))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
