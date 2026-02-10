import os
import logging
import json
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
    # For development, you can hardcode it temporarily (remove in production)
    # TOKEN = "YOUR_BOT_TOKEN_HERE"

PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

# Conversation states
ASKING_QUESTIONS = 1

# Questions data
QUESTIONS = [
    {
        "question": "What's your age group?",
        "options": ["Under 18", "18-25", "26-35", "36-50", "51+"]
    },
    {
        "question": "How often do you shop online?",
        "options": ["Daily", "Weekly", "Monthly", "Rarely", "Never"]
    },
    {
        "question": "What's your favorite social media platform?",
        "options": ["Instagram", "TikTok", "Facebook", "Twitter", "YouTube"]
    },
    {
        "question": "What type of products are you most interested in?",
        "options": ["Electronics", "Fashion", "Home & Kitchen", "Beauty", "Sports"]
    },
    {
        "question": "How much do you typically spend online per month?",
        "options": ["Under $50", "$50-$100", "$100-$200", "$200-$500", "$500+"]
    }
]

# Simple in-memory storage (for production, use a database)
user_sessions = {}

class UserSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.current_question = 0
        self.answers = []
        self.started_at = datetime.now()
        self.completed = False
    
    def add_answer(self, answer):
        self.answers.append(answer)
        self.current_question += 1
        
        if self.current_question >= len(QUESTIONS):
            self.completed = True
            return True
        return False

# Initialize Flask app
app = Flask(__name__)

# Initialize Telegram bot application
try:
    if TOKEN:
        application = Application.builder().token(TOKEN).build()
        logger.info("Telegram bot application initialized successfully")
    else:
        application = None
        logger.error("Cannot initialize bot without token")
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    application = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user completed recently
    if user_id in user_sessions and user_sessions[user_id].completed:
        last_session = user_sessions[user_id]
        time_since = datetime.now() - last_session.started_at
        
        if time_since < timedelta(days=7):
            days_left = 7 - time_since.days
            await update.message.reply_text(
                f"⏳ You've already completed this week's questions!\n"
                f"Please come back in {days_left} day{'s' if days_left > 1 else ''} for new questions.\n\n"
                f"In the meantime, you can review your previous answers with /review"
            )
            return ConversationHandler.END
    
    # Start new session
    user_sessions[user_id] = UserSession(user_id)
    
    await update.message.reply_text(
        "🎯 **Welcome to our Digital Marketing Survey!**\n\n"
        "We have 5 quick questions to better understand your preferences.\n"
        "Each question has multiple-choice options - just tap to answer!\n\n"
        "Let's get started with the first question:"
    )
    
    await ask_question(update, context)
    return ASKING_QUESTIONS

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("Please start with /start")
        return ConversationHandler.END
    
    session = user_sessions[user_id]
    
    if session.current_question < len(QUESTIONS):
        question_data = QUESTIONS[session.current_question]
        question_text = question_data["question"]
        options = question_data["options"]
        
        # Create keyboard
        keyboard = [[option] for option in options]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"**Question {session.current_question + 1}/{len(QUESTIONS)}**\n\n"
            f"{question_text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("Please start with /start")
        return ConversationHandler.END
    
    answer = update.message.text
    session = user_sessions[user_id]
    
    # Validate answer
    current_options = QUESTIONS[session.current_question]["options"]
    if answer not in current_options:
        await update.message.reply_text("Please select one of the provided options.")
        return ASKING_QUESTIONS
    
    # Add answer
    is_completed = session.add_answer({
        "question": QUESTIONS[session.current_question]["question"],
        "answer": answer,
        "timestamp": datetime.now().isoformat()
    })
    
    if is_completed:
        await update.message.reply_text(
            "✅ **Thank you for completing all questions!**\n\n"
            "Your answers have been recorded successfully.\n\n"
            "🔔 **Please come back next week for new questions!**\n\n"
            "You can review your answers anytime with /review",
            reply_markup=None
        )
        
        logger.info(f"User {user_id} completed survey")
        return ConversationHandler.END
    else:
        await ask_question(update, context)
        return ASKING_QUESTIONS

async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions or not user_sessions[user_id].answers:
        await update.message.reply_text(
            "You haven't completed any questions yet. Start with /start"
        )
        return
    
    session = user_sessions[user_id]
    answers_text = "📋 **Your Answers:**\n\n"
    
    for i, answer in enumerate(session.answers, 1):
        answers_text += f"{i}. **{answer['question']}**\n"
        answers_text += f"   👉 {answer['answer']}\n\n"
    
    if session.completed:
        time_since = datetime.now() - session.started_at
        days_left = max(0, 7 - time_since.days)
        answers_text += f"⏳ **Next survey available in:** {days_left} day{'s' if days_left != 1 else ''}"
    
    await update.message.reply_text(answers_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Survey cancelled. You can start again anytime with /start"
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Marketing Survey Bot Help**\n\n"
        "Available commands:\n"
        "/start - Start the survey\n"
        "/review - Review your answers\n"
        "/help - Show this help message\n\n"
        "The survey has 5 questions and takes about 1 minute to complete."
    )

# Flask routes
@app.route('/')
def home():
    return "Telegram Marketing Bot is running! ✅"

@app.route('/health')
def health():
    return {"status": "healthy", "bot_initialized": application is not None}

@app.route(f'/webhook/{TOKEN}' if TOKEN else '/webhook', methods=['POST'])
async def webhook():
    """Handle incoming updates from Telegram"""
    if application is None:
        return "Bot not initialized", 500
    
    update = Update.de_json(await request.get_json(), application.bot)
    
    # Process the update
    await application.process_update(update)
    
    return 'ok'

def setup_bot():
    """Setup bot handlers and webhook"""
    if application is None:
        logger.error("Cannot setup bot without token")
        return
    
    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASKING_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('review', review))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('start', start))
    
    # Set webhook if WEBHOOK_URL is provided
    if WEBHOOK_URL and TOKEN:
        webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
        logger.info(f"Setting webhook to: {webhook_url}")
        
        # Run in async context
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def set_webhook_async():
            await application.bot.set_webhook(url=webhook_url)
            logger.info("Webhook set successfully")
        
        loop.run_until_complete(set_webhook_async())

@app.route('/set_webhook')
def set_webhook_route():
    """Manually trigger webhook setup"""
    if not TOKEN:
        return "Bot token not set", 400
    
    setup_bot()
    return "Webhook setup triggered"

if __name__ == '__main__':
    # Setup bot handlers
    if application:
        setup_bot()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=PORT, debug=False)
