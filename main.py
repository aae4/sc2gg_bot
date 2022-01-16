from telegram.ext import Updater
import logging
from bot.scripts import settings

from bot.handlers import (
  start_handler,
  stream_monitor_handler,
  message_handler,
  replay_handler
)

# logger
logging.basicConfig(
  format = '%(asctime)s - %(levelname)s - %(message)s',
  datefmt = '%d.%m.%Y %I:%M:%S %p',
  level = logging.INFO
)

# updater
updater = Updater(settings.TOKEN)
dispatcher = updater.dispatcher

def bound_handlers():
  dispatcher.add_handler(start_handler)
  dispatcher.add_handler(stream_monitor_handler)
  dispatcher.add_handler(message_handler)
  dispatcher.add_handler(replay_handler)

def main():
  # setting up application
  bound_handlers()
  # configure_database()

  # long polling on development
  if settings.DEBUG:
    updater.start_polling()

if __name__ == '__main__':
  main()
