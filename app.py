"""
CiviLink Main Application
Flask application for WhatsApp + Telegram government services assistant
"""

from flask import Flask, request, jsonify, Response
import logging
import os
from dotenv import load_dotenv

from core.assistant import CiviLinkAssistant
from privacy.consent_manager import ConsentManager, ConsentType
from whatsapp.twilio_handler import TwilioWebhookHandler
from multilingual.multilingual_llm import MultilingualLLM

from telegram import Bot
from telegram.error import TelegramError

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# -----------------------------
# Flask app
# -----------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-secret-key")

# -----------------------------
# Initialize components
# -----------------------------
assistant = CiviLinkAssistant()
consent_manager = ConsentManager()
multilingual_llm = MultilingualLLM()
twilio_handler = TwilioWebhookHandler()

# Telegram bot
telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
bot = Bot(token=telegram_token) if telegram_token else None
if not bot:
    logger.warning("Telegram bot token not set!")

# =========================================================
# HOME
# =========================================================

@app.route('/')
def home():
    return jsonify({
        "service": "CiviLink Assistant",
        "status": "running",
        "channels": ["WhatsApp", "Telegram"]
    })


# =========================================================
# WHATSAPP WEBHOOK
# =========================================================

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        data = request.form.to_dict()

        logger.info(f"WhatsApp message from {data.get('From')}")

        twiml_response = twilio_handler.process_message(
            data,
            assistant,
            consent_manager
        )

        return Response(twiml_response, mimetype='text/xml')

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {str(e)}")
        return Response(
            "<Response><Message>Error occurred</Message></Response>",
            mimetype='text/xml'
        )


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():

    try:
        update = request.get_json(silent=True) or {}

        logger.info("Telegram update received")

        if "message" not in update:
            return jsonify({"status": "ignored"}), 200

        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = str(message["from"]["id"])
        text = message.get("text", "")

        if not text:
            return jsonify({"status": "empty message"}), 200

        logger.info(f"Telegram message: {text}")

        result = assistant.process_message(user_id, text)
        response_text = result.get("response", "Sorry, I couldn't understand.")

        if not bot:
            logger.warning("TELEGRAM_TOKEN not set; cannot reply to Telegram")
            return jsonify({"status": "no_bot"}), 200

        bot.send_message(chat_id=chat_id, text=response_text)
        return jsonify({"status": "ok"}), 200

    except TelegramError as te:
        logger.exception(f"Telegram API error: {te}")
        return jsonify({"status": "telegram_error"}), 200

    except Exception as e:
        logger.exception(f"Telegram webhook error: {e}")
        return jsonify({"status": "server_error"}), 200


# =========================================================
# DIRECT API MESSAGE
# =========================================================

@app.route('/api/message', methods=['POST'])
def process_message():

    try:

        data = request.get_json()

        user_id = data.get("user_id")
        message = data.get("message")

        if not user_id or not message:
            return jsonify({"error": "user_id and message required"}), 400

        result = assistant.process_message(user_id, message)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Message processing error: {e}")
        return jsonify({"error": "failed"}), 500


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route('/api/health')
def health():

    return jsonify({
        "status": "healthy",
        "service": "CiviLink"
    })


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    port = int(os.getenv("PORT", 5000))

    logger.info("Starting CiviLink server...")

    app.run(
        host="0.0.0.0",
        port=port
    )