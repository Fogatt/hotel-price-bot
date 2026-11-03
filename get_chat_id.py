"""Print the chat id(s) that have messaged your bot.

1. Send any message (e.g. "hi") to your bot in Telegram.
2. Run:  TELEGRAM_BOT_TOKEN=123:abc python get_chat_id.py
"""

import json
import os
import urllib.request

token = os.environ["TELEGRAM_BOT_TOKEN"]
with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates") as r:
    updates = json.load(r).get("result", [])

chats = {}
for u in updates:
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat")
    if chat:
        chats[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name")

if not chats:
    print("No messages found. Send a message to your bot first, then run this again.")
for cid, name in chats.items():
    print(f"chat id: {cid}  ({name})")
