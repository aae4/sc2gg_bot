from telegram import Update, ParseMode
from telegram.ext import CallbackContext
from ..constants import Keyboard
import time
from ..scripts.youtube import check_streams_status, show_current_status
from ..scripts.settings import SC2_CHAT_ID

STREAM_MONITOR_ACTIVE = True

def start_command_callback(update: Update, context: CallbackContext):
  context.bot.send_message(
    chat_id = update.effective_chat.id,
    text = 'Hello!', parse_mode = ParseMode.HTML,
    reply_markup = Keyboard.main
  )

def stream_monitor_callback(update: Update, context: CallbackContext):
  chat_id = update.effective_chat.id if (update.effective_chat.id > 0 or len(context.args) == 0) else SC2_CHAT_ID

  global STREAM_MONITOR_ACTIVE

  if len(context.args) == 0:
    text = show_current_status()

    context.bot.send_message(
      chat_id = update.effective_chat.id,
      text = text,
      parse_mode = ParseMode.HTML,
    )
  else:
    if context.args[0] == '1':
      context.bot.send_message(
        chat_id = update.effective_chat.id,
        text = 'Stream Monitor STARTED',
        parse_mode = ParseMode.HTML
      )
      STREAM_MONITOR_ACTIVE = True
    elif context.args[0] == '0':
      STREAM_MONITOR_ACTIVE = False
      context.bot.send_message(
        chat_id = update.effective_chat.id,
        text = 'Stream Monitor STOPED',
        parse_mode = ParseMode.HTML
      )

  counter = 0
  while STREAM_MONITOR_ACTIVE:
    if not STREAM_MONITOR_ACTIVE:
      break

    msgs = check_streams_status()
    if len(msgs) > 0:
      text = '\n'.join(msgs)
      context.bot.send_message(
        chat_id = update.effective_chat.id,
        text = text, parse_mode = ParseMode.HTML
      )
    time.sleep(10)

