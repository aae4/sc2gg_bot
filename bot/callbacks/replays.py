from telegram import Update, ParseMode
from telegram.ext import CallbackContext
from ..scripts.html_generator import Exporter
import sc2reader

def replay_handler(update: Update, context: CallbackContext):
  doc = update.message.document
  if doc.file_name.count('.SC2Replay') > 0:
    replay = context.bot.getFile(update.message.document)
    replay.download(custom_path=f'./files/{doc.file_name}')

    path = f'./files/{doc.file_name}'
    exporter = Exporter(path)
    result = exporter.run()

    if result['status']:
      message = f"Report successfully generated and will be uploaded in a minute: <a href='{result['url']}'>{result['filename']}</a>"
    else:
      message = result['message']

    # context.bot.sendDocument(chat_id = update.effective_chat.id,
    #                          document = open('./files/out.pdf', 'rb'))

    # sc2replay = sc2reader.load_replay(f'./files/{doc.file_name}')
    # result = formatReplay(sc2replay)
    context.bot.send_message(
      chat_id = update.effective_chat.id,
      text = message,
      parse_mode = ParseMode.HTML,
    )
