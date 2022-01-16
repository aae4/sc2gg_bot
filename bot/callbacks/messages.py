from telegram import Update, ParseMode
from telegram.ext import CallbackContext

def message_handler_callback(update: Update, context: CallbackContext):
  context.bot.send_message(
    chat_id = update.effective_chat.id,
    text = update.message.text
  )

def replay_handler(update: Update, context: CallbackContext):
  doc = update.message.document
  if doc.file_name.count('.SC2Replay') > 0:
    replay = context.bot.getFile(update.message.document)
    replay.download(custom_path=f'./files/{doc.file_name}')

  # doc = update.message.document.
  # print(doc.file_name)
  # print(doc.mime_type)
  # if doc:
  #   print('WRITE FILE')
  #   with open(f'{doc.file_name}', 'w') as f:
  #     context.bot.get_file(update.message.document).download(out=f)
