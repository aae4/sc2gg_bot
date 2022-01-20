from configparser import ConfigParser
import os

# parse config
config = ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '../../config.ini'))

# project section
DEBUG = config.getboolean('project', 'debug')

# bot section
TOKEN = config.get('bot', 'token')
ADMINS = tuple(map(int, config.get('bot', 'admins').split(',')))
DEVELOPER = config.getint('bot', 'developer')
SC2_CHAT_ID = config.getint('bot', 'sc2chatId')

UPLOADED_REPORT_URL = config.get('project', 'uploaded_report_url')
PROJECT_PATH = config.get('project', 'project_path')
ICONS_PATH = config.get('project', 'icons_path')
SRC_URL_PATH = config.get('project', 'src_url_path')
PAGES_GIT_PATH = config.get('project', 'pages_git_path')
HTML_STORE_PATH = config.get('project', 'html_store_path')
REPLAY_STORE_PATH = config.get('project', 'replay_store_path')
STORE_REPLAYS_COUNT = config.getint('project', 'store_replays_count')

STORE_REPLAYS_COUNT = config.getint('project', 'store_replays_count')

# # database section
# SQLITE_PATH = config.get('database', 'sqlite')

# # server section
# LISTEN = config.get('server', 'listen')
# HOST = config.get('server', 'host')
# PORT = config.getint('server', 'port')

# # webhook section
# WEBHOOK_URL = config.get('webhook', 'webhook_url')
# PKEY_PATH = config.get('webhook', 'Pkey_path')
# CERT_PATH = config.get('webhook', 'cert_path')
