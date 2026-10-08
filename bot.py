import os
import json
import random
import asyncio
import logging
import threading
from flask import Flask
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Config
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN", "YOUR_MASTER_BOT_TOKEN")
DATA_FILE = "tokens.json"

# Reactions Array (আপনার দেওয়া লিস্ট)
MY_EMOJIS = [
    "👍", "👾", "❤️", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", 
    "💀", "😢", "🎉", "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡", 
    "🥱", "🥴", "😍", "🐳", "❤️‍🔥", "🌚", "🌭", "💯", "🤣", "⚡", 
    "🍌", "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "😈", "😴", 
    "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨", "🤝", 
    "✍️", "🤗", "🫡", "🎅", "🎄", "💅", "🤪", "🗿", "🆒", "💘", 
    "🙉", "🦄", "😘", "💊", "🙊", "😎"
]

# Flask App for Render Keep-Alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Reaction Bot Server is running fine!"

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Token Storage Helpers
def load_tokens() -> list:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading tokens: {e}")
        return []

def save_tokens(tokens: list):
    with open(DATA_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

class BotAdmin(StatesGroup):
    waiting_for_token = State()

def get_admin_keyboard():
    tokens = load_tokens()
    kb = [
        [InlineKeyboardButton(text="➕ Add Bot Token", callback_data="add_token")],
        [InlineKeyboardButton(text=f"📋 View Bots ({len(tokens)})", callback_data="list_tokens")],
        [InlineKeyboardButton(text="🗑️ Clear All Bots", callback_data="clear_tokens")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

dp = Dispatcher(storage=MemoryStorage())
master_bot = Bot(token=MASTER_BOT_TOKEN)

# Direct HTTP POST method (just like your JS code)
async def send_reaction_http(session: aiohttp.ClientSession, bot_token: str, chat_id: int, message_id: int):
    url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
    chosen_emoji = random.choice(MY_EMOJIS)
    
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [
            {
                "type": "emoji",
                "emoji": chosen_emoji
            }
        ],
        "is_big": True
    }

    try:
        async with session.post(url, json=payload, timeout=10) as response:
            res_json = await response.json()
            if res_json.get("ok"):
                logger.info(f"✅ Bot ({bot_token[:8]}...) reacted with {chosen_emoji}")
            else:
                logger.error(f"❌ Telegram Error ({bot_token[:8]}...): {res_json.get('description')}")
    except Exception as e:
        logger.error(f"Request failed for {bot_token[:8]}...: {e}")

# Apply reactions to post using child bots
async def apply_reactions(chat_id: int, message_id: int):
    tokens = load_tokens()
    logger.info(f"Channel post received! ID: {message_id} in {chat_id}. Reacting with {len(tokens)} bots.")
    
    if not tokens:
        return

    async with aiohttp.ClientSession() as session:
        tasks = []
        for t in tokens:
            tasks.append(send_reaction_http(session, t, chat_id, message_id))
            await asyncio.sleep(0.15)  # Telegram API flood control
        await asyncio.gather(*tasks)

# Admin Handlers
@dp.message(Command("start"))
async def start_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ আপনি এই বটের অ্যাডমিন নন।")
        return
    await message.reply(
        "👋 **Reaction Bot Admin Panel**\nনিচের বাটন থেকে চাইল্ড বট নিয়ন্ত্রণ করুন:",
        reply_markup=get_admin_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "add_token")
async def add_token_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Unauthorized", show_alert=True)
    await state.set_state(BotAdmin.waiting_for_token)
    await call.message.edit_text("🤖 চাইল্ড বটের Token পাঠান:")
    await call.answer()

@dp.message(BotAdmin.waiting_for_token)
async def process_token_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    token = message.text.strip()
    
    # Simple check via API
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                res = await resp.json()
                if res.get("ok"):
                    username = res["result"]["username"]
                    tokens = load_tokens()
                    if token not in tokens:
                        tokens.append(token)
                        save_tokens(tokens)
                        await message.reply(f"✅ বট যোগ হয়েছে: @{username}", reply_markup=get_admin_keyboard())
                    else:
                        await message.reply("⚠️ এই টোকেনটি আগে থেকেই যুক্ত আছে।", reply_markup=get_admin_keyboard())
                else:
                    await message.reply("❌ অবৈধ টোকেন! BotFather থেকে সঠিক টোকেন দিন।", reply_markup=get_admin_keyboard())
    except Exception as e:
        await message.reply(f"❌ চেক করতে সমস্যা হয়েছে: {e}", reply_markup=get_admin_keyboard())
    finally:
        await state.clear()

@dp.callback_query(F.data == "list_tokens")
async def list_tokens_callback(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Unauthorized", show_alert=True)
    tokens = load_tokens()
    if not tokens:
        await call.message.edit_text("ℹ️ কোনো চাইল্ড বট এখনও যোগ করা হয়নি।", reply_markup=get_admin_keyboard())
        return

    text = f"🤖 **যুক্ত করা চাইল্ড বট ({len(tokens)} টি):**\n\n"
    for i, t in enumerate(tokens, 1):
        text += f"{i}. `{t[:10]}...{t[-5:]}`\n"
    await call.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "clear_tokens")
async def clear_tokens_callback(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Unauthorized", show_alert=True)
    save_tokens([])
    await call.message.edit_text("🗑️ সব চাইল্ড বট মুছে ফেলা হয়েছে।", reply_markup=get_admin_keyboard())
    await call.answer()

# Channel post listener
@dp.channel_post()
async def on_channel_post(message: Message):
    await apply_reactions(chat_id=message.chat.id, message_id=message.message_id)

async def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    logger.info("Bot starting polling...")
    await dp.start_polling(master_bot, allowed_updates=["message", "callback_query", "channel_post"])

if __name__ == "__main__":
    asyncio.run(main())
