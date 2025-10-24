#!/usr/bin/env python3
"""
Telegram Bot for formatting episode links - Webhook Version for Render
Install dependencies: pip install python-telegram-bot flask
Run: python3 bot.py
"""

import re
import logging
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import asyncio
from threading import Thread

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get configuration from environment
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "")  # Render provides this
PORT = int(os.environ.get("PORT", 10000))  # Render provides this

# Store user data temporarily
user_sessions = {}

# Flask app for webhook
app = Flask(__name__)

def parse_bulk_output(text):
    """Parse the bulk upload output and extract episode links by quality"""
    episodes = {}
    pattern = r'S(\d+)-E(\d+).*?(480|720|1080).*?(https://t\.me/[^\s]+)'
    matches = re.finditer(pattern, text)
    
    for match in matches:
        season = match.group(1)
        episode = match.group(2)
        quality = match.group(3)
        url = match.group(4).strip()
        
        ep_key = f"E{episode.zfill(2)}"
        
        if ep_key not in episodes:
            episodes[ep_key] = {}
        
        episodes[ep_key][quality] = url
    
    return episodes

def format_output(episodes):
    """Format episodes into the desired output with hyperlinks"""
    output_lines = []
    sorted_eps = sorted(episodes.items(), key=lambda x: int(x[0][1:]))
    bold_nums = str.maketrans('0123456789', '𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗')
    
    for ep_num, qualities in sorted_eps:
        quality_links = []
        
        for quality in ['480', '720', '1080']:
            if quality in qualities:
                bold_quality = f"{quality}𝐏".translate(bold_nums)
                quality_links.append(f'<a href="{qualities[quality]}">{bold_quality}</a>')
            else:
                bold_quality = f"{quality}𝐏".translate(bold_nums)
                quality_links.append(f"<s>{bold_quality}</s>")
        
        bold_ep = ep_num.translate(bold_nums)
        line = f"➪ {bold_ep}      {quality_links[0]}      {quality_links[1]}       {quality_links[2]}"
        output_lines.append(line)
    
    return '\n'.join(output_lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = (
        "👋 <b>Welcome to Episode Link Formatter Bot!</b>\n\n"
        "📝 <b>How to use:</b>\n"
        "1. Use /upload to start collecting links\n"
        "2. Forward/paste all your bulk upload messages (480p, 720p, 1080p)\n"
        "3. Use /format to generate the formatted output\n"
        "4. Use /cancel to cancel current upload session\n\n"
        "Type /help for more details!"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = (
        "📚 <b>Help Guide:</b>\n\n"
        "<b>Commands:</b>\n"
        "/upload - Start collecting episode links\n"
        "/format - Generate formatted output\n"
        "/cancel - Cancel current session\n"
        "/clear - Clear all collected links\n"
        "/status - Check current session status\n\n"
        "<b>Workflow:</b>\n"
        "1. Send /upload command\n"
        "2. Paste all three bulk uploads (480p, 720p, 1080p)\n"
        "3. Send /format to get the final output\n\n"
        "The bot will combine all qualities into a single formatted output!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start upload session"""
    user_id = update.effective_user.id
    user_sessions[user_id] = {'collecting': True, 'messages': []}
    
    await update.message.reply_text(
        "✅ <b>Upload mode activated!</b>\n\n"
        "📥 Now you can forward or paste all your bulk upload messages.\n"
        "Send them all (480p, 720p, 1080p sections).\n\n"
        "When done, use /format to generate the output.",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"User {user_id} started upload session")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current upload session"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        del user_sessions[user_id]
        await update.message.reply_text(
            "❌ Upload session cancelled.\nUse /upload to start a new session.",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"User {user_id} cancelled upload session")
    else:
        await update.message.reply_text(
            "ℹ️ No active upload session.\nUse /upload to start collecting links.",
            parse_mode=ParseMode.HTML
        )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear collected messages"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        user_sessions[user_id]['messages'] = []
        await update.message.reply_text(
            "🗑️ All collected links cleared.\n"
            "You can continue pasting new links or use /format with current data.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "ℹ️ No active session. Use /upload to start.",
            parse_mode=ParseMode.HTML
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check session status"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions and user_sessions[user_id]['collecting']:
        msg_count = len(user_sessions[user_id]['messages'])
        await update.message.reply_text(
            f"📊 <b>Session Status:</b>\n\n"
            f"✅ Upload mode: Active\n"
            f"📝 Messages collected: {msg_count}\n\n"
            f"Use /format to generate output\n"
            f"Use /cancel to stop collecting",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "ℹ️ No active upload session.\nUse /upload to start collecting links.",
            parse_mode=ParseMode.HTML
        )

async def collect_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect messages during upload session"""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions or not user_sessions[user_id]['collecting']:
        return
    
    user_text = update.message.text
    user_sessions[user_id]['messages'].append(user_text)
    msg_count = len(user_sessions[user_id]['messages'])
    
    await update.message.reply_text(
        f"✅ Message collected! ({msg_count} total)\n"
        f"Continue pasting or use /format when done.",
        parse_mode=ParseMode.HTML
    )
    
    logger.info(f"User {user_id} added message #{msg_count}")

async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Format all collected messages into final output"""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text(
            "❌ No upload session found.\nUse /upload to start collecting links first.",
            parse_mode=ParseMode.HTML
        )
        return
    
    messages = user_sessions[user_id]['messages']
    
    if not messages:
        await update.message.reply_text(
            "❌ No messages collected yet.\n"
            "Paste your bulk upload outputs first, then use /format.",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        combined_text = '\n'.join(messages)
        episodes = parse_bulk_output(combined_text)
        
        if not episodes:
            await update.message.reply_text(
                "❌ No valid episode links found in collected messages.\n"
                "Please check your input format.",
                parse_mode=ParseMode.HTML
            )
            return
        
        formatted_output = format_output(episodes)
        header = "✅ <b>Formatted Episode Links:</b>\n\n"
        footer = f"\n\n📊 Total Episodes: {len(episodes)}"
        full_output = header + formatted_output + footer
        
        await update.message.reply_text(
            full_output,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        logger.info(f"Formatted {len(episodes)} episodes for user {user_id}")
        del user_sessions[user_id]
        
        await update.message.reply_text(
            "🎉 Session completed! Use /upload to start a new one.",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error formatting links: {e}")
        await update.message.reply_text(
            f"❌ An error occurred while formatting:\n{str(e)}\n\n"
            "Please try again or use /cancel to reset.",
            parse_mode=ParseMode.HTML
        )

# Initialize bot application
application = None

async def initialize_bot():
    """Initialize the bot application"""
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("upload", upload_command))
    application.add_handler(CommandHandler("format", format_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_messages))
    
    await application.initialize()
    await application.start()
    
    # Set webhook
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

@app.route('/')
def index():
    """Health check endpoint"""
    return "Bot is running!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming updates from Telegram"""
    try:
        json_data = request.get_json()
        update = Update.de_json(json_data, application.bot)
        asyncio.run(application.process_update(update))
        return "OK", 200
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return "Error", 500

def run_flask():
    """Run Flask server"""
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n⚠️  ERROR: Please set BOT_TOKEN environment variable!")
        print("Get your token from @BotFather on Telegram\n")
    else:
        # Initialize bot
        asyncio.run(initialize_bot())
        
        # Start Flask server
        logger.info(f"🤖 Bot webhook server starting on port {PORT}...")
        run_flask()
