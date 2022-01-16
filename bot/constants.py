from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

class Keyboard:
  main = ReplyKeyboardMarkup([
      ['/start']
  ], resize_keyboard=True)
