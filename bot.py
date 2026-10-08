import os
import json
import random
import asyncio
import logging
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReactionTypeEmoji
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # আপনার Telegram User ID দিন
MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN", "YOUR_MASTER_BOT_TOKEN")
DATA_FILE = "tokens.json"

# Reactions to choose from
REACTIONS = ["❤️", "🔥", "👍", "🎉", "👏"]

# Simple Flask web server for Render health checks
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
    except Exception:
        return []

def save_tokens(tokens: list):
    with open(DATA_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

# FSM States
class BotAdmin(StatesGroup):
    waiting_for_token = State()

# Keyboards
def get_admin_keyboard():
    tokens = load_tokens()
    kb = [
        [InlineKeyboardButton(text="➕ Add Bot Token", callback_data="add_token")],
        [InlineKeyboardButton(text=f"📋 View Bots ({len(tokens)})", callback_data="list_tokens")],
        [InlineKeyboardButton(text="🗑️ Clear All Bots", callback_data="clear_tokens")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Dispatcher & Bot
dp = Dispatcher(storage=MemoryStorage())
master_bot = Bot(token=MASTER_BOT_TOKEN)

# Send reactions concurrently using child bots
async def apply_reactions(chat_id: int, message_id: int):
    tokens = load_tokens()
    if not tokens:
        logger.info("No child bots configured.")
        return

    async def react(token: str):
        temp_bot = None
        try:
            temp_bot = Bot(token=token)
            emoji = random.choice(REACTIONS)
            await temp_bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)]
            )
            logger.info(f"Reacted with {emoji} via {token[:10]}...")
        except TelegramAPIError as e:
            logger.error(f"Telegram error on token {token[:10]}...: {e}")
        except Exception as e:
            logger.error(f"Error on token {token[:10]}...: {e}")
        finally:
            if temp_bot:
                await temp_bot.session.close()

    tasks = [react(t) for t in tokens]
    await asyncio.gather(*tasks, return_exceptions=True)

# Handlers
@dp.message(Command("start"))
async def start_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ আপনি এই বটের অ্যাডমিন নন।")
        return
    await message.reply("👋 **Reaction Bot Admin Panel**\nনিচের মেনু থেকে চাইল্ড বট নিয়ন্ত্রণ করুন:", reply_markup=get_admin_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "add_token")
async def add_token_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Unauthorized", show_alert=True)
    await state.set_state(BotAdmin.waiting_for_token)
    await call.message.edit_text("🤖 চাইল্ড বটের Token পাঠান (BotFather থেকে পাওয়া):")
    await call.answer()

@dp.message(BotAdmin.waiting_for_token)
async def process_token_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    token = message.text.strip()
    
    # Test token validity
    test_bot = Bot(token=token)
    try:
        bot_info = await test_bot.get_me()
        tokens = load_tokens()
        if token not in tokens:
            tokens.append(token)
            save_tokens(tokens)
            await message.reply(f"✅ সফলভাবে বট যোগ হয়েছে: @{bot_info.username}", reply_markup=get_admin_keyboard())
        else:
            await message.reply("⚠️ এই টোকেনটি আগেই যোগ করা আছে।", reply_markup=get_admin_keyboard())
    except Exception as e:
        await message.reply(f"❌ অবৈধ টোকেন! BotFather থেকে সঠিক টোকেন কপি করুন। ত্রুটি: {e}", reply_markup=get_admin_keyboard())
    finally:
        await test_bot.session.close()
        await state.clear()

@dp.callback_query(F.data == "list_tokens")
async def list_tokens_callback(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Unauthorized", show_alert=True)
    tokens = load_tokens()
    if not tokens:
        await call.message.edit_text("ℹ️ কোনো চাইল্ড বট এখনও যোগ করা হয়নি।", reply_markup=get_admin_keyboard())
        return

    text = f"🤖 **যুক্ত করা বট তালিকা ({len(tokens)} টি):**\n\n"
    for i, t in enumerate(tokens, 1):
        text += f"{i}. `{t[:10]}...{t[-5:]}`\n"
    await call.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "clear_tokens")
async def clear_tokens_callback(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Unauthorized", show_alert=True)
    save_tokens([])
    await call.message.edit_text("🗑️ সব চাইল্ড বট ডিলিট করা হয়েছে।", reply_markup=get_admin_keyboard())
    await call.answer()

# Channel post listener
@dp.channel_post()
async def channel_post_listener(message: Message):
    # Channel এ নতুন পোস্ট আসলে চাইল্ড বটগুলো অটো রিঅ্যাক্ট দেবে
    await apply_reactions(chat_id=message.chat.id, message_id=message.message_id)

async def main():
    # Start web server thread for Render
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    logger.info("Bot starting polling...")
    await dp.start_polling(master_bot)

if __name__ == "__main__":
    asyncio.run(main())
