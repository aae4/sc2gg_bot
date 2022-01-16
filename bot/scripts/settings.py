from configparser import ConfigParser
import os

# parse config
config = ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '../../config.ini'))

# project section
DEBUG = config.get('project', 'debug')

# bot section
TOKEN = config.get('bot', 'token')
ADMINS = tuple(map(int, config.get('bot', 'admins').split(',')))
DEVELOPER = config.getint('bot', 'developer')


SC2PAGES_PATH = config.get('project', 'sc2pages_path')
PAGES_URL = config.get('project', 'pages_url')
PROJECT_PATH = config.get('project', 'project_path')
SAVE_ICONS_PATH = config.get('project', 'save_icons_path')
ICON_PATH = config.get('project', 'icon_path')
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