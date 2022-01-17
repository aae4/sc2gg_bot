from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, Filters
from .callbacks import *

start_handler = CommandHandler(
  command = 'start',
  callback = start_command_callback,
)

stream_monitor_handler = CommandHandler(
  command = 'stream_monitor',
  callback = stream_monitor_callback,
  filters = Filters.group,
  run_async=True
)


message_handler = MessageHandler(
  Filters.text & ~Filters.command, message_handler_callback
)

replay_handler = MessageHandler(Filters.document & Filters.group, replay_handler)
