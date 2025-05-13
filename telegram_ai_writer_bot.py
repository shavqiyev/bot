import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)
import google.generativeai as genai

# === CONFIGURATION ===
GEMINI_API_KEY = "AIzaSyD_OseIo1lKG5hNMakfdmTf66S4QYbRRm4"
TELEGRAM_BOT_TOKEN = "7809448220:AAH9PSt0rakqteOkah9OAxVwKSFGQruEJB8"
CHANNEL_ID = "@test_uz_a"
USER_ID = 123456789  # <-- replace this with your Telegram ID

REGENERATE_LIMIT = 3
TOPIC_FILE = "topics.txt"

genai.configure(api_key=GEMINI_API_KEY)
user_state = {}

# === Helpers ===
def load_topics():
    try:
        with open(TOPIC_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_topics(topics):
    with open(TOPIC_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(topics))

# === Gemini post generation ===
def generate_telegram_post(topic):
    prompt = f"""Sen O'zbekistonliklar uchun Telegram blog post yozuvchi kontent yaratuvchisan.
Mavzu: "{topic}"

Qoidalar:
- Telegram uslubida yoz (bold sarlavhalar, emoji, ro'yxatlar bilan)
- Sodda, qiziqarli va 300-500 so‘z
- Xulosa bilan yakunla"""
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    return response.text

# === Preview with buttons ===
async def send_preview(context, uid, topic, content, regen_count):
    keyboard = [
        [InlineKeyboardButton("✅ Publish", callback_data="approve"),
         InlineKeyboardButton("🔁 Regenerate", callback_data="regenerate")],
        [InlineKeyboardButton("✏️ Edit", callback_data="edit"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=uid,
        text=f"📄 *{topic}*\n\n{content}\n\n📝 Choose:",
        parse_mode="Markdown",
        reply_markup=markup
    )

# === /blog {topic} ===
async def blog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /blog {topic}")
        return
    topic = " ".join(context.args)
    content = generate_telegram_post(topic)
    user_state[update.effective_user.id] = {"topic": topic, "content": content, "regen_count": 0}
    await send_preview(context, update.effective_user.id, topic, content, 0)

# === /post_now from topics.txt ===
async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = load_topics()
    if not topics:
        await update.message.reply_text("📭 Topic list is empty.")
        return
    topic = topics[0]
    content = generate_telegram_post(topic)
    user_state[update.effective_user.id] = {"topic": topic, "content": content, "regen_count": 0, "from_list": True}
    await send_preview(context, update.effective_user.id, topic, content, 0)

# === Button decisions ===
async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if uid not in user_state:
        await query.edit_message_text("❗ No active post.")
        return

    data = user_state[uid]
    topic = data["topic"]
    content = data["content"]
    regen_count = data.get("regen_count", 0)
    from_list = data.get("from_list", False)

    if query.data == "approve":
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"📌 *{topic}*\n\n{content}",
            parse_mode="Markdown"
        )
        await query.edit_message_text("✅ Published.")
        if from_list:
            topics = load_topics()
            if topics and topics[0] == topic:
                topics.pop(0)
                save_topics(topics)
        user_state.pop(uid)

    elif query.data == "regenerate":
        regen_count += 1
        if regen_count >= REGENERATE_LIMIT:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"📌 *{topic}*\n\n{content}",
                parse_mode="Markdown"
            )
            await query.edit_message_text(f"✅ Auto-published after {REGENERATE_LIMIT} regenerations.")
            if from_list:
                topics = load_topics()
                if topics and topics[0] == topic:
                    topics.pop(0)
                    save_topics(topics)
            user_state.pop(uid)
        else:
            new_content = generate_telegram_post(topic)
            user_state[uid] = {"topic": topic, "content": new_content, "regen_count": regen_count, "from_list": from_list}
            await query.edit_message_text("🔄 Regenerated!")
            await send_preview(context, uid, topic, new_content, regen_count)

    elif query.data == "edit":
        await query.edit_message_text("✏️ Please send your custom post text now.")
        user_state[uid]["editing"] = True

    elif query.data == "cancel":
        await query.edit_message_text("❌ Canceled.")
        user_state.pop(uid)

# === Custom text after Edit ===
async def handle_custom_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state or "editing" not in user_state[uid]:
        return

    custom_content = update.message.text
    topic = user_state[uid]["topic"]
    from_list = user_state[uid].get("from_list", False)

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"📌 *{topic}*\n\n{custom_content}",
        parse_mode="Markdown"
    )
    await update.message.reply_text("✅ Custom post published.")
    if from_list:
        topics = load_topics()
        if topics and topics[0] == topic:
            topics.pop(0)
            save_topics(topics)
    user_state.pop(uid)

# === /add_topic {topic} ===
async def add_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /add_topic {topic}")
        return
    new_topic = " ".join(context.args)
    topics = load_topics()
    topics.append(new_topic)
    save_topics(topics)
    await update.message.reply_text(f"✅ Added: {new_topic}")

# === /list_topics ===
async def list_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = load_topics()
    if not topics:
        await update.message.reply_text("📭 Topic list is empty.")
        return
    msg = "\n".join([f"{i+1}. {t}" for i, t in enumerate(topics)])
    await update.message.reply_text(f"📋 Topics:\n{msg}")

# === /delete_topic {number} ===
async def delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❗ Usage: /delete_topic {number}")
        return
    index = int(context.args[0]) - 1
    topics = load_topics()
    if 0 <= index < len(topics):
        removed = topics.pop(index)
        save_topics(topics)
        await update.message.reply_text(f"✅ Deleted: {removed}")
    else:
        await update.message.reply_text("❗ Invalid topic number.")

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot ready: /blog, /post_now, /add_topic, /list_topics, /delete_topic")

# === Main run ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🤖 Bot running...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("blog", blog_command))
    app.add_handler(CommandHandler("post_now", post_now))
    app.add_handler(CommandHandler("add_topic", add_topic))
    app.add_handler(CommandHandler("list_topics", list_topics))
    app.add_handler(CommandHandler("delete_topic", delete_topic))
    app.add_handler(CallbackQueryHandler(handle_decision))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_text))

    app.run_polling()
