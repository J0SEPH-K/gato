# Source Generated with Decompyle++
# File: notify.pyc (Python 3.11)

from __future__ import annotations
import threading

try:
    import requests
except Exception:
    requests = None


class Notifier:
    
    def __init__(self, get_discord, get_ntfy, log, get_tag):
        self._get_discord = get_discord
        self._get_ntfy = get_ntfy
        self._log = log
        self._get_tag = get_tag or (lambda: 'Gato_super')

    
    def _tag(self) -> str:
        return (self._get_tag() or 'Gato_super').strip()

    
    def text(self, msg: str) -> None:
        if not requests:
            return None
        body = f'''[{self._tag()}] {msg}'''
        dc = (self._get_discord() or '').strip()
        nt = (self._get_ntfy() or '').strip()
        if dc:
            threading.Thread(target = self._send_discord, args = (dc, body), daemon = True).start()
        if nt:
            threading.Thread(target = self._send_ntfy, args = (nt, body), daemon = True).start()
        return None

    
    def image(self, msg: str, img_bgr, name: str = 'capture.jpg') -> None:
        if not requests:
            return None
        body = f'''[{self._tag()}] {msg}'''
        dc = (self._get_discord() or '').strip()
        nt = (self._get_ntfy() or '').strip()
        if dc:
            if img_bgr is not None:
                threading.Thread(target = self._send_discord_image, args = (dc, body, img_bgr, name), daemon = True).start()
            else:
                threading.Thread(target = self._send_discord, args = (dc, body), daemon = True).start()
        if nt:
            threading.Thread(target = self._send_ntfy, args = (nt, body), daemon = True).start()
        return None

    
    def _send_discord(self, url: str, body: str) -> None:
        
        try:
            requests.post(url, json = {
                'content': body }, timeout = 5)
            return None
        except Exception as e:
            self._log(f'''디스코드 알림 실패: {e}''')
            return None


    
    def _send_discord_image(self, url: str, body: str, img_bgr, name: str) -> None:
        
        try:
            import cv2
            import numpy as np
            (ok, buf) = cv2.imencode('.jpg', np.ascontiguousarray(img_bgr), [
                cv2.IMWRITE_JPEG_QUALITY,
                80])
            if ok:
                requests.post(url, data = {
                    'content': body }, files = {
                    'file': (name, buf.tobytes(), 'image/jpeg') }, timeout = 12)
                return None
            requests.post(url, json = {
                'content': body }, timeout = 5)
            return None
        except Exception as e:
            self._log(f'''디스코드 이미지 실패: {e}''')
            return None


    
    def _send_ntfy(self, topic: str, body: str) -> None:
        
        try:
            requests.post(ntfy_url(topic), data = body.encode('utf-8'), timeout = 5)
            return None
        except Exception as e:
            self._log(f'''ntfy 알림 실패: {e}''')
            return None




def ntfy_url(topic: str) -> str:
    topic = (topic or '').strip().strip('/')
    if not topic:
        return ''
    if topic.startswith(('http://', 'https://')):
        return topic
    return 'https://ntfy.sh/' + topic

_DISCORD_API = 'https://discord.com/api/v10'

class BotPoller(threading.Thread):
    
    def __init__(self, get_token, get_channel, on_message, log, poll):
        super().__init__(daemon = True)
        self.get_token = get_token
        self.get_channel = get_channel
        self.on_message = on_message
        self.log = log
        self.poll = poll
        self._last_id = None
        self._cur_channel = None
        self._stop_event = threading.Event()
        self._session = requests.Session() if requests else None

    
    def stop(self):
        self._stop_event.set()

    
    @staticmethod
    def _retry_after(r, default, cap):
        try:
            v = r.headers.get('Retry-After')
            if v is None:
                try:
                    v = (r.json() or { }).get('retry_after')
                except Exception:
                    v = None
            return max(1.0, min(cap, float(v)))
        except (TypeError, ValueError):
            return default

    def _get(self, token, path):
        return self._session.get(f'''{_DISCORD_API}{path}''', headers = {
            'Authorization': f'''Bot {token}''' }, timeout = 6)

    
    def _newest(self, token, channel):
        
        try:
            d = self._get(token, f'''/channels/{channel}/messages?limit=1''').json()
            if isinstance(d, list) and d:
                return d[0]['id']
        except Exception:
            pass


    
    def run(self):
        if not self._session:
            return None
        while self.get_token() and self.get_channel():
            token = (self.get_token() or '').strip()
            channel = (self.get_channel() or '').strip()
            if not token or not channel:
                continue
            
            try:
                if self._cur_channel != channel:
                    self._cur_channel = channel
                    self._last_id = self._newest(token, channel)
                url = f'''/channels/{channel}/messages?limit=10'''
                if self._last_id:
                    url += f'''&after={self._last_id}'''
                r = self._get(token, url)
                if r.status_code == 429:
                    wait = self._retry_after(r)
                    self.log(f'''[디코] 요청 과다(429) — {wait:.0f}초 대기 (봇 토큰을 여러 PC가 공유하면 상시 발생)''')
                    self._stop_event.wait(wait)
                    continue
                if r.status_code != 200:
                    self.log(f'''[디코] 응답 {r.status_code} — 토큰/채널/인텐트 확인''')
                    self._stop_event.wait(10)
                    continue
                msgs = r.json()
                if not isinstance(msgs, list):
                    continue
                if not self._last_id:
                    if msgs:
                        self._last_id = msgs[0]['id']
                    continue
                for m in reversed(msgs):
                    self._last_id = m['id']
                    try:
                        if m.get('author', {}).get('bot'):
                            continue
                        content = (m.get('content') or '').strip()
                        author = m.get('author', {}).get('username', '?')
                        self.on_message(content, author)
                    except Exception as e:
                        self.log(f'''[디코] 메시지 처리 오류: {e}''')
                        continue
                    except Exception as e:
                        self.log(f'''[디코] 폴링 오류: {e}''')
                    if self._stop_event.wait(self.poll):
                        return None
            except Exception as e:
                self.log(f'''[디코] 폴링 오류: {e}''')
                self._stop_event.wait(5)

