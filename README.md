# Hotel price bot

Every hour, a GitHub Action searches hotels with [LiteAPI](https://liteapi.travel) and sends you a Telegram message listing the hotels whose price per night is **at or below** your maximum. If nothing matches, no message is sent.

## Setup

### 1. Create the Telegram bot
1. In Telegram, open **@BotFather** and send `/newbot`. Pick a name and a username ending in `bot`.
2. BotFather replies with a **token** like `123456789:AA...`. Keep it secret.
3. Open your new bot and send it any message (e.g. `hi`).
4. Get your chat id:
   ```bash
   TELEGRAM_BOT_TOKEN=123456789:AA... python get_chat_id.py
   ```
   (Or open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy `chat.id`.)

### 2. Get a LiteAPI key
Sign up at liteapi.travel. Use the `sand_...` key for testing and the `prod_...` key for real prices.

### 3. Add GitHub secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `LITEAPI_KEY` | your LiteAPI key |
| `TELEGRAM_BOT_TOKEN` | token from BotFather |
| `TELEGRAM_CHAT_ID` | your chat id |

Or with the GitHub CLI:
```bash
gh secret set LITEAPI_KEY
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
```

### 4. Test it
**Actions → Check hotel prices → Run workflow.** After that it runs every hour on its own.

## Configure searches
Edit `config.json`. You can add several searches:

```json
{
  "name": "Fernando de Noronha - December",
  "latitude": -3.8547, "longitude": -32.4247, "radius_meters": 15000,
  "checkin": "2026-12-10", "checkout": "2026-12-14",
  "adults": 2, "currency": "BRL", "guest_nationality": "BR",
  "max_price_per_night": 1500
}
```

Instead of coordinates you can use `"country_code": "BR", "city_name": "Recife"`.

### Only check specific hotels / pousadas
By name (part of the name is enough; upper/lower case and accents are ignored):
```json
"hotel_names": ["Maravilha", "Zé Maria", "Teju-Açu"]
```
By LiteAPI hotel ID (exact; no area needed):
```json
"hotel_ids": ["lp1a2b3", "lp4c5d6"]
```
Leave both out (or empty) to check every hotel in the area.
To see the names and IDs LiteAPI has for your area:
```bash
LITEAPI_KEY=sand_... python list_hotels.py
```
A name that matches nothing is reported in the Action log.
Searches whose check-in date has passed are skipped.

## Run locally
```bash
LITEAPI_KEY=sand_... DRY_RUN=1 python bot.py
```
`DRY_RUN=1` prints the message instead of sending it to Telegram.

## Notes
- Prices are the cheapest available room for the whole stay, divided by the number of nights.
- Scheduled workflows in a repo with no activity for 60 days are paused by GitHub; re-enable them in the Actions tab.
