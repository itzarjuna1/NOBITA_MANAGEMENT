import html
import json
import re
import requests
from typing import Optional

from telegram import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
    Update,
    User,
)
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
)
from telegram.utils.helpers import mention_html

import AloneRobot.modules.sql.chatbot_sql as sql
from AloneRobot import BOT_ID, BOT_NAME, BOT_USERNAME, dispatcher

from AloneRobot.modules.helper_funcs.chat_status import user_admin, user_admin_no_reply
from AloneRobot.modules.log_channel import gloggable


@user_admin_no_reply
@gloggable
def alonerm(update: Update, context: CallbackContext) -> str:
    query: Optional[CallbackQuery] = update.callback_query
    user: Optional[User] = update.effective_user
    match = re.match(r"rm_chat\((.+?)\)", query.data)

    if match:
        chat: Optional[Chat] = update.effective_chat
        sql.set_alone(chat.id)

        return (
            f"<b>{html.escape(chat.title)}:</b>\n"
            f"ᴀɪ ᴅɪsᴀʙʟᴇᴅ\n"
            f"<b>ᴀᴅᴍɪɴ :</b> {mention_html(user.id, html.escape(user.first_name))}\n"
        )

    return ""


@user_admin_no_reply
@gloggable
def aloneadd(update: Update, context: CallbackContext) -> str:
    query: Optional[CallbackQuery] = update.callback_query
    user: Optional[User] = update.effective_user
    match = re.match(r"add_chat\((.+?)\)", query.data)

    if match:
        chat: Optional[Chat] = update.effective_chat
        sql.rem_alone(chat.id)

        return (
            f"<b>{html.escape(chat.title)}:</b>\n"
            f"ᴀɪ ᴇɴᴀʙʟᴇᴅ\n"
            f"<b>ᴀᴅᴍɪɴ :</b> {mention_html(user.id, html.escape(user.first_name))}\n"
        )

    return ""


@user_admin
@gloggable
def alone(update: Update, context: CallbackContext):
    msg = "• ᴄʜᴏᴏsᴇ ᴏᴘᴛɪᴏɴ ᴛᴏ ᴇɴᴀʙʟᴇ/ᴅɪsᴀʙʟᴇ ᴄʜᴀᴛʙᴏᴛ"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ᴇɴᴀʙʟᴇ", callback_data="add_chat(1)"),
                InlineKeyboardButton("ᴅɪsᴀʙʟᴇ", callback_data="rm_chat(1)"),
            ]
        ]
    )

    update.effective_message.reply_text(
        text=msg,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


def alone_message(context: CallbackContext, message):
    if not message.text:
        return False

    text = message.text.lower()
    reply_message = message.reply_to_message

    if text == "alone":
        return True

    if BOT_USERNAME.lower() in text:
        return True

    if reply_message and reply_message.from_user:
        if reply_message.from_user.id == BOT_ID:
            return True

    return False


OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = "sk-or-your-key-here"


def get_ai_reply(text: str):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": text}],
    }

    try:
        res = requests.post(OPENROUTER_API, headers=headers, json=payload, timeout=10)
        data = res.json()
        return data["choices"][0]["message"]["content"]
    except:
        return "⚠️ AI is currently unavailable."


def chatbot(update: Update, context: CallbackContext):
    message = update.effective_message
    chat_id = update.effective_chat.id

    if sql.is_alone(chat_id):
        return

    if not alone_message(context, message):
        return

    context.bot.send_chat_action(chat_id, action="typing")

    reply = get_ai_reply(message.text)

    message.reply_text(reply)


CHATBOTK_HANDLER = CommandHandler("chatbot", alone, run_async=True)
ADD_CHAT_HANDLER = CallbackQueryHandler(aloneadd, pattern=r"add_chat", run_async=True)
RM_CHAT_HANDLER = CallbackQueryHandler(alonerm, pattern=r"rm_chat", run_async=True)

CHATBOT_HANDLER = MessageHandler(
    Filters.text
    & (~Filters.regex(r"^#[^\s]+"))
    & (~Filters.regex(r"^!"))
    & (~Filters.regex(r"^/")),
    chatbot,
    run_async=True,
)

dispatcher.add_handler(ADD_CHAT_HANDLER)
dispatcher.add_handler(CHATBOTK_HANDLER)
dispatcher.add_handler(RM_CHAT_HANDLER)
dispatcher.add_handler(CHATBOT_HANDLER)

__handlers__ = [
    ADD_CHAT_HANDLER,
    CHATBOTK_HANDLER,
    RM_CHAT_HANDLER,
    CHATBOT_HANDLER,
    ]
