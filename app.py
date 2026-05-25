# ADMIN BREXX
# JOIN OUR CHANNEL 
# https://t.me/bloodbrx98





import os
import asyncio
import binascii
import json
import random
import urllib.parse
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Set, Tuple

import aiohttp
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Import your protobuf modules
import like_pb2
import like_count_pb2
import uid_generator_pb2

# ---------- Configuration ----------
KEY_LIMIT = 90
BOT_TOKEN = "8614926866:AAF_vDRsOdMrgBcKWMPLt3us0Sz1ycsFJaM"

# User rate limiting (Telegram user_id -> [count, reset_timestamp])
user_tracker: Dict[int, Tuple[int, float]] = defaultdict(lambda: [0, time.time()])

# Cache which accounts liked which UID (to avoid re-liking)
liked_cache: Dict[str, Set[str]] = defaultdict(set)

# ---------- JSON Account Loader ----------
def load_accounts_json(server_name: str) -> list:
    """Load accounts from JSON file based on server"""
    try:
        if server_name == "IND":
            filename = "accounts_ind.json"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            filename = "accounts_br.json"
        else:  # BD, RU etc.
            filename = "accounts_bd.json"

        if not os.path.exists(filename):
            # Try fallback
            print(f"⚠️ {filename} not found, trying accounts_ind.json")
            filename = "accounts_ind.json"
            if not os.path.exists(filename):
                print("❌ No account JSON file found")
                return []

        with open(filename, "r") as f:
            data = json.load(f)
            accounts = []
            for uid, password in data.items():
                if uid and password:
                    accounts.append({"uid": uid.strip(), "password": password.strip()})
            return accounts
    except Exception as e:
        print(f"Error loading accounts from JSON: {e}")
        return []

# ---------- Helper Functions (unchanged) ----------
def get_today_midnight_timestamp() -> float:
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day)
    return midnight.timestamp()

def encrypt_message(plaintext: bytes) -> str:
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded)).decode('utf-8')

def create_protobuf_message(user_id: int, region: str) -> bytes:
    msg = like_pb2.like()
    msg.uid = user_id
    msg.region = region
    return msg.SerializeToString()

def enc(uid: str) -> str:
    msg = uid_generator_pb2.uid_generator()
    msg.krishna_ = int(uid)
    msg.teamXdarks = 1
    return encrypt_message(msg.SerializeToString())

def decode_protobuf(binary: bytes):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except:
        return None

def get_player_info(encrypted_uid: str, server_name: str, token: str):
    if server_name == "IND":
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB53"
    }
    try:
        resp = requests.post(url, data=edata, headers=headers, timeout=10, verify=False)
        return decode_protobuf(resp.content)
    except:
        return None

async def generate_jwt_token(uid: str, password: str) -> str | None:
    try:
        encoded_pwd = urllib.parse.quote(password)
        url = f"https://jwtforme.vercel.app/semy?uid={uid}&password={encoded_pwd}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=24) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, dict):
                        return data.get('token') or data.get('token')
        return None
    except:
        return None

async def send_like(encrypted_uid: str, token: str, url: str) -> int:
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=5) as resp:
                return resp.status
    except:
        return 500

async def process_account(target_uid: str, encrypted_uid: str, account: dict,
                          url: str, semaphore: asyncio.Semaphore) -> Tuple[int, str]:
    async with semaphore:
        token = await generate_jwt_token(account['uid'], account['password'])
        if not token:
            return 500, account['uid']
        status = await send_like(encrypted_uid, token, url)
        if status == 200:
            liked_cache[target_uid].add(account['uid'])
        return status, account['uid']

async def send_all_likes(target_uid: str, server_name: str, like_url: str) -> dict:
    region = server_name
    proto_msg = create_protobuf_message(int(target_uid), region)
    encrypted_uid = encrypt_message(proto_msg)

    accounts = load_accounts_json(server_name)
    if not accounts:
        return {'success': 0, 'failed': 0, 'total': 0, 'already_liked': 0}

    already = liked_cache.get(target_uid, set())
    fresh = [acc for acc in accounts if acc['uid'] not in already]

    if not fresh:
        return {
            'success': 0, 'failed': 0, 'total': len(accounts),
            'already_liked': len(already), 'fresh_used': 0
        }

    random.shuffle(fresh)
    semaphore = asyncio.Semaphore(25)
    tasks = [process_account(target_uid, encrypted_uid, acc, like_url, semaphore)
             for acc in fresh[:2000]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = 0
    failed = 0
    for r in results:
        if isinstance(r, tuple):
            status, _ = r
            if status == 200:
                successful += 1
            else:
                failed += 1

    return {
        'success': successful,
        'failed': failed,
        'total': len(accounts),
        'already_liked': len(already),
        'fresh_used': len(fresh[:2000])
    }

# ---------- Telegram Handlers with Beautiful Design ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Create inline keyboard for server selection
    keyboard = [
        [InlineKeyboardButton("🇮🇳 IND Server", callback_data="server_IND"),
         InlineKeyboardButton("🇧🇷 BR Server", callback_data="server_BR")],
        [InlineKeyboardButton("🇺🇸 US/SAC/NA", callback_data="server_US"),
         InlineKeyboardButton("🇧🇩 BD/RU Server", callback_data="server_BD")],
        [InlineKeyboardButton("📊 My Status", callback_data="status"),
         InlineKeyboardButton("🔄 Reset Cache (Admin)", callback_data="reset_cache")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✨ <b>🔥 FREE FIRE LIKE BOT 🔥</b> ✨\n\n"
        "🎮 <b>Send unlimited likes to any Free Fire profile!</b>\n"
        "⚡ Powered by premium account pool\n"
        "🛡️ 100% Safe & Fast\n\n"
        "👇 <b>Click a button below to start</b> 👇",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("server_"):
        server = data.split("_")[1]
        context.user_data['selected_server'] = server
        await query.edit_message_text(
            f"✅ <b>Server selected: {server}</b>\n\n"
            f"Now send your like command like this:\n"
            f"<code>/like &lt;UID&gt; {server}</code>\n\n"
            f"Example: <code>/like 123456789 {server}</code>",
            parse_mode="HTML"
        )
    elif data == "status":
        # Show user status
        user_id = update.effective_user.id
        today_ts = get_today_midnight_timestamp()
        count, last_reset = user_tracker[user_id]
        if last_reset < today_ts:
            count = 0
            user_tracker[user_id] = [0, time.time()]
        remaining = max(0, KEY_LIMIT - count)
        await query.edit_message_text(
            f"<b>📊 YOUR LIKE LIMIT TODAY</b>\n\n"
            f"✅ <b>Used:</b> {count}/{KEY_LIMIT}\n"
            f"⏳ <b>Remaining:</b> {remaining}\n"
            f"🔄 Resets at midnight (server time)\n\n"
            f"💡 Use /like command to send likes!",
            parse_mode="HTML"
        )
    elif data == "reset_cache":
        # Admin only check
        ADMIN_ID = 123456789  # CHANGE THIS
        if update.effective_user.id != ADMIN_ID:
            await query.edit_message_text("⛔ <b>Admin only command!</b>", parse_mode="HTML")
            return
        global liked_cache
        liked_cache.clear()
        await query.edit_message_text("🧹 <b>Cache cleared successfully!</b>", parse_mode="HTML")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today_ts = get_today_midnight_timestamp()
    count, last_reset = user_tracker[user_id]
    if last_reset < today_ts:
        count = 0
        user_tracker[user_id] = [0, time.time()]
    remaining = max(0, KEY_LIMIT - count)
    await update.message.reply_text(
        f"📊 <b>Your like limit today</b>\n\n"
        f"✅ Used: <code>{count}/{KEY_LIMIT}</code>\n"
        f"⏳ Remaining: <code>{remaining}</code>\n"
        f"🔄 Resets at midnight (server time)",
        parse_mode="HTML"
    )

async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) != 2:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/like &lt;UID&gt; &lt;SERVER&gt;</code>\n\n"
            "Example: <code>/like 123456789 IND</code>\n\n"
            "Use /start to see server buttons.",
            parse_mode="HTML"
        )
        return

    uid, server = args[0], args[1].upper()
    valid_servers = ["IND", "BR", "US", "SAC", "NA", "BD", "RU"]
    if server not in valid_servers:
        await update.message.reply_text(
            f"❌ <b>Invalid server!</b>\nValid: {', '.join(valid_servers)}",
            parse_mode="HTML"
        )
        return

    # Daily limit check
    today_ts = get_today_midnight_timestamp()
    count, last_reset = user_tracker[user_id]
    if last_reset < today_ts:
        user_tracker[user_id] = [0, time.time()]
        count = 0
    if count >= KEY_LIMIT:
        await update.message.reply_text(
            f"❌ <b>Daily limit reached!</b> ({KEY_LIMIT}/{KEY_LIMIT})\nTry again tomorrow.",
            parse_mode="HTML"
        )
        return

    processing_msg = await update.message.reply_text(
        "🔄 <b>Processing likes...</b>\nPlease wait, this may take a few seconds.",
        parse_mode="HTML"
    )

    try:
        accounts = load_accounts_json(server)
        if not accounts:
            await processing_msg.edit_text("❌ <b>No accounts found for this server!</b>", parse_mode="HTML")
            return

        # Get a working token
        check_token = None
        for acc in accounts[:5]:
            check_token = await generate_jwt_token(acc['uid'], acc['password'])
            if check_token:
                break

        if not check_token:
            await processing_msg.edit_text("❌ <b>Token generation failed!</b>\nServer might be down.", parse_mode="HTML")
            return

        encrypted_uid = enc(uid)
        before = get_player_info(encrypted_uid, server, check_token)
        if before is None:
            await processing_msg.edit_text("❌ <b>Invalid UID or server!</b>\nPlease check and try again.", parse_mode="HTML")
            return

        before_data = json.loads(MessageToJson(before))
        before_likes = int(before_data['AccountInfo'].get('Likes', 0))

        # Determine like URL
        if server == "IND":
            like_url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif server in {"BR", "US", "SAC", "NA"}:
            like_url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            like_url = "https://clientbp.ggpolarbear.com/LikeProfile"

        result = await send_all_likes(uid, server, like_url)

        after = get_player_info(encrypted_uid, server, check_token)
        if after is None:
            await processing_msg.edit_text("❌ <b>Could not verify likes after command!</b>", parse_mode="HTML")
            return

        after_data = json.loads(MessageToJson(after))
        after_likes = int(after_data['AccountInfo'].get('Likes', 0))
        player_name = after_data['AccountInfo'].get('PlayerNickname', 'Unknown')
        player_id = after_data['AccountInfo'].get('UID', uid)

        likes_given = after_likes - before_likes
        if likes_given > 0:
            user_tracker[user_id][0] += 1

        remaining = KEY_LIMIT - user_tracker[user_id][0]

        # Beautiful result message
        response = (
            f"✨ <b>✅ LIKE REQUEST COMPLETED</b> ✨\n\n"
            f"🎮 <b>Player:</b> <code>{player_name}</code>\n"
            f"🆔 <b>UID:</b> <code>{player_id}</code>\n"
            f"🌍 <b>Server:</b> {server}\n\n"
            f"❤️ <b>Likes Given:</b> <code>{likes_given}</code>\n"
            f"📈 <b>Before → After:</b> <code>{before_likes} → {after_likes}</code>\n\n"
            f"📊 <b>Account Stats:</b>\n"
            f"   ✅ Success: {result['success']}\n"
            f"   ❌ Failed: {result['failed']}\n"
            f"   🔄 Fresh used: {result['fresh_used']}/{result['total']}\n"
            f"   ⏭️  Already liked by {result['already_liked']} accounts\n\n"
            f"🎟️ <b>Your Remaining Likes Today:</b> <code>{remaining}/{KEY_LIMIT}</code>\n\n"
            f"💡 Use /like again or click /start for menu"
        )
        await processing_msg.edit_text(response, parse_mode="HTML")

    except Exception as e:
        await processing_msg.edit_text(f"❌ <b>Error:</b>\n<code>{str(e)}</code>", parse_mode="HTML")

async def reset_cache_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ADMIN_ID = 7898402627  # CHANGE THIS TO YOUR USER ID
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command!")
        return
    global liked_cache
    liked_cache.clear()
    await update.message.reply_text("🧹 Cache cleared successfully!")

# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("like", like_command))
    app.add_handler(CommandHandler("reset_cache", reset_cache_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Free Fire Like Bot Started!")
    print("📁 Using JSON account files: accounts_ind.json, accounts_br.json, accounts_bd.json")
    app.run_polling()

if __name__ == "__main__":
    main()
