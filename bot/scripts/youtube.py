import requests
import time

CHANNELS_LIST = [
  {'type': 'yt', 'name': 'Yaroslav', 'url': 'https://www.youtube.com/channel/UCvRgzENBHuPzw1q1Tkrlv2g', 'status': False},
  {'type': 'yt', 'name': 'Aslan', 'url': 'https://www.youtube.com/channel/UCbO1SWl9ecT811mwvr_tKYA', 'status': False},
  {'type': 'yt', 'name': 'Vanya', 'url': 'https://www.youtube.com/channel/UCyYR1zpk_An1RhaHfjI6S9A', 'status': False},
  {'type': 'yt', 'name': 'David', 'url': 'https://www.youtube.com/channel/UCVFkJ-isHV0b6j-9QfcQ0xw', 'status': False},
  {'type': 'yt', 'name': 'Fadi', 'url': 'https://www.youtube.com/channel/UCUEgAACAefmjn2SuMvs-xLw', 'status': False},
  {'type': 'yt', 'name': 'David', 'url': 'https://www.youtube.com/channel/UCn2yfnPlaB5wZcPPXpLB-Aw', 'status': False},
  # {'type': 'yt', 'name': 'AslanTest', 'url': 'https://www.youtube.com/channel/UC-a7iMZ4zIwFVEaaIcVS9tg', 'status': False},
  # {'type': 'yt', 'name': 'Chess.com', 'url': 'https://www.youtube.com/channel/UC5kS0l76kC0xOzMPtOmSFGw', 'status': False},
  # {'type': 'tw', 'name': 'Vasiliy', 'url': 'https://www.twitch.tv/augmode', 'status': False},
  # {'type': 'tw', 'name': 'Fadi', 'url': 'https://www.twitch.tv/fuda163', 'status': False},
  # {'type': 'tw', 'name': 'David', 'url': 'https://www.twitch.tv/inshock93', 'status': False},
  # {'type': 'tw', 'name': 'Chess.com', 'url': 'https://www.twitch.tv/chess', 'status': False}
  # {'type': 'tw', 'name': '', 'url': '', 'status': False},
]

  # {'name': '', 'url': '', 'status': False},
  # {'name': '', 'url': '', 'status': False},


def is_streaming(ch_type, url):
  if ch_type == 'yt':
    k1 = '"isLive":true'
    k2 = '"isLiveBroadcast":true'
    k3 = 'livePlayerConfig'
    r = requests.get(url + '/live')
    if (k1 in r.text or k2 in r.text) and k3 in r.text:
      return True
    else:
      return False
  else:
    return False;

def is_streamingOld(ch_type, url):
  if ch_type == 'yt':
    keyword = 'hqdefault_live.jpg'
    r1 = requests.get(url)
    r2 = requests.get(url + '/videos')
    if keyword in r1.text or keyword in r2.text:
      return True
    else:
      return False
  else:
    r = requests.get(url)
    keyword = '"isLiveBroadcast":true'
    if keyword in r.text:
      return True
    else:
      return False

def show_current_status():
  msgs = []
  for ch in CHANNELS_LIST:
    if ch['status'] == True:
      msgs.append(f"<b>{ch['name']}</b> is <b>ONLINE</b> now: <a href='{ch['url']}/live'>Watch</a>")

  if len(msgs) == 0:
    msgs = ["No active streams :("]

  return '\n'.join(msgs)

def check_streams_status():
  global CHANNELS_LIST

  msgs = []
  for ch in CHANNELS_LIST:
    old_status = ch['status']
    status = is_streaming(ch['type'], ch['url'])

    if not old_status and status:
      # print(f"Channel {ch['name']} is ONLINE now")
      msgs.append(f"<b>{ch['name']}</b> is <b>ONLINE</b> now: <a href='{ch['url']}/live'>Go-go!</a>")
    elif old_status and not status:
      msgs.append(f"<b>{ch['name']}</b> is <b>OFFLINE</b>. :(")

    if old_status != status:
      ch['status'] = status

  return msgs

# "isLive": true

# "liveBroadcastDetails":{"isLiveNow":true #!!!!!

# "ownerChannelName": "ThirtyVirus",
# "liveBroadcastDetails": {
#   "isLiveNow": true,
#   "startTimestamp": "2022-01-18T18:59:35+00:00"
# },

# live1 = 'https://www.youtube.com/c/ThirtyVirus/live'
# url = 'https://www.youtube.com/c/TheJoves/live'
# responses = requests.get(url)
# print(responses.text)
# for response in responses.history:
#     print(response.url)

# print('not live')
# responses = requests.get("https://www.youtube.com/channel/UCvRgzENBHuPzw1q1Tkrlv2g/live")
# for response in responses.history:
#     print(response.url)
# r = requests.get('https://www.twitch.tv/chess')
# print(r.text)
# while True:
#   msgs = check_streams_status()
#   if len(msgs) > 0:
#     text = '\n'.join(msgs)
#     print(text)
#   time.sleep(2)
