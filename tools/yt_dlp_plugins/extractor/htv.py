import os
import sys
import json
import time
import urllib.request
from base64 import urlsafe_b64encode, urlsafe_b64decode

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Hash import SHA256
    from Cryptodome.Random import get_random_bytes
except ImportError:
    try:
        from Crypto.Cipher import AES  # type: ignore
        from Crypto.Hash import SHA256  # type: ignore
        from Crypto.Random import get_random_bytes  # type: ignore
    except ImportError:
        AES = None
        SHA256 = None
        get_random_bytes = None

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, urljoin


def _get_default_user_agent():
    ua_file = os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "flaresolverr_ua.txt")
    if os.path.isfile(ua_file):
        try:
            with open(ua_file, "r", encoding="utf-8") as f:
                ua = f.read().strip()
                if ua:
                    return ua
        except Exception:
            pass
    return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'


USER_AGENT = _get_default_user_agent()


def into_base64(o):
    return urlsafe_b64encode(o).decode('ascii').rstrip('=')

def from_base64(o):
    if isinstance(o, str):
        o = o.encode('ascii', errors='ignore')

    return urlsafe_b64decode(o.ljust((len(o) // 4 + 1) * 4, b'='))


try:
    from ._sitekit import SiteKit
except ImportError:
    try:
        from _sitekit import SiteKit
    except ImportError:
        class SiteKit:
            SITE_NAME = "hanime.tv"
            ENGINE = "native"
            QUALITY_CEILING = 1080
            REQUIRES_COOKIES = True
            PREFERRED_BROWSERS = ("helium", "brave", "chrome", "edge")
            EXTRA_YTDL_OPTS = {}
            @classmethod
            def ytdl_opts(cls):
                return {
                    "format": f"bestvideo[height<=?{cls.QUALITY_CEILING}]+bestaudio/best[height<=?{cls.QUALITY_CEILING}]/best",
                    "concurrent_fragment_downloads": 16,
                }


def _get_clipboard_stream(video_id):
    """Retrieve direct M3U8 stream URL from Windows clipboard if captured by browser helper."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        CF_UNICODETEXT = 13
        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                text = ctypes.wstring_at(ptr).strip()
                if ('http://' in text or 'https://' in text) and (
                    '.m3u8' in text or '.mp4' in text or '/manifest' in text or 'vids.hanime.tv' in text or 'weeb.hanime.tv' in text
                ):
                    return text
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        pass
    return None


def _solve_via_flaresolverr(url):
    """Query local FlareSolverr instance to solve Cloudflare Turnstile automatically."""
    endpoint = "http://localhost:8191/v1"

    # Check if running; if not, try to start from C:\Tools\FlareSolverr\flaresolverr.exe
    is_running = False
    try:
        req_health = urllib.request.Request("http://localhost:8191", headers={"User-Agent": "mpv-config/1.0"})
        with urllib.request.urlopen(req_health, timeout=1.0) as r:
            is_running = True
    except Exception:
        is_running = False

    if not is_running:
        exe_candidates = [
            r"C:\Tools\FlareSolverr\flaresolverr.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\FlareSolverr\flaresolverr.exe"),
            os.environ.get("FLARESOLVERR_PATH", ""),
        ]
        for exe in exe_candidates:
            if exe and os.path.isfile(exe):
                try:
                    import subprocess
                    flags = 0
                    if sys.platform == "win32":
                        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                    subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    for _ in range(15):
                        time.sleep(0.5)
                        try:
                            with urllib.request.urlopen("http://localhost:8191", timeout=1.0) as r:
                                is_running = True
                                break
                        except Exception:
                            pass
                    if is_running:
                        break
                except Exception:
                    pass

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps({"cmd": "request.get", "url": url, "maxTimeout": 60000}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=70) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "ok":
                sol = data.get("solution", {})
                cookies = sol.get("cookies", [])
                ua = sol.get("userAgent", "")
                cstr = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))

                # Auto-save fresh cookies to disk for future yt-dlp runs
                try:
                    lines = ["# Netscape HTTP Cookie File", "# Exported by FlareSolverr", ""]
                    for c in cookies:
                        dom = c.get("domain", ".hanime.tv")
                        sec = "TRUE" if c.get("secure") else "FALSE"
                        lines.append(f"{dom}\tTRUE\t/\t{sec}\t{int(c.get('expiry') or 0)}\t{c.get('name')}\t{c.get('value')}")
                    netscape_text = "\n".join(lines) + "\n"
                    save_targets = [
                        os.path.join(os.environ.get("APPDATA", ""), "yt-dlp", "cookies.txt"),
                        os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "cookies", "hanime.tv.txt"),
                    ]
                    for st in save_targets:
                        os.makedirs(os.path.dirname(st), exist_ok=True)
                        with open(st, "w", encoding="utf-8") as f:
                            f.write(netscape_text)

                    if ua:
                        ua_file = os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "flaresolverr_ua.txt")
                        os.makedirs(os.path.dirname(ua_file), exist_ok=True)
                        with open(ua_file, "w", encoding="utf-8") as f:
                            f.write(ua)
                except Exception:
                    pass

                return {"cookie_str": cstr, "user_agent": ua, "cookies": cookies}
    except Exception:
        pass
    return None


class HanimeTVIE(SiteKit, InfoExtractor):
    IE_NAME = 'hanime'
    SITE_NAME = 'hanime.tv'
    ENGINE = 'native'
    REQUIRES_COOKIES = True
    _VALID_URL = r'https?://(?:www\.)?hanime\.tv/(?:videos/hentai|hentai/video|playlists/[0-9a-z]+/video)/(?P<id>[0-9a-z\-]+)'
    _AES_KEY = bytes.fromhex("5d657a4dcb0bad1c637ff2e221059b10ff17ae39fe855003e846918941f4ebe3")
    _AES_HEADER = bytes.fromhex("6874762d696e7365637572652d7631")

    _TESTS = [{
        'url': 'https://hanime.tv/videos/hentai/itadaki-seieki',
        'info_dict': {
            'id': 'itadaki-seieki',
            'ext': 'mp4',
            'title': 'Itadaki! Seieki',
        },
        'params': {
            'skip_download': True,
        }
    }]

    @classmethod
    def _digest_token(cls, o):
        o = json.dumps(o)
        iv = get_random_bytes(12)

        cipher = AES.new(cls._AES_KEY, AES.MODE_GCM, iv)
        cipher.update(cls._AES_HEADER)
        ciphertext, tag = cipher.encrypt_and_digest(o.encode('utf-8'))

        return into_base64(json.dumps({
            'v': 1,
            'alg': 'AES-256-GCM',
            'iv': into_base64(iv),
            'tag': into_base64(tag),
            'data': into_base64(ciphertext)
        }).encode('utf-8'))

    @classmethod
    def _parse_token(cls, o):
        o = json.loads(from_base64(o))

        cipher = AES.new(cls._AES_KEY, AES.MODE_GCM, from_base64(o['iv']))
        cipher.update(cls._AES_HEADER)
        plaintext = cipher.decrypt_and_verify(from_base64(o['data']), from_base64(o['tag']))

        return json.loads(plaintext.decode('utf-8'))

    @classmethod
    def _generate_credentials_local(cls):
        ts = int(time.time())
        digest = SHA256.new(f'{ts},Xkdi29,https://hanime.tv,mn2,{ts}'.encode('utf-8')).hexdigest()
        return digest, ts

    def _get_cached_m3u8(self, video_id):
        """Query clipboard, local MPV sync daemon, and active streams file for intercepted M3U8 manifest."""
        # 1. Immediate clipboard check (zero network dependency)
        clip_stream = _get_clipboard_stream(video_id)
        if clip_stream:
            return clip_stream

        # 2. Local HTTP Daemon
        try:
            req = urllib.request.Request(f'http://127.0.0.1:8765/stream?slug={video_id}')
            with urllib.request.urlopen(req, timeout=0.5) as r:
                data = json.loads(r.read().decode('utf-8'))
                if data.get('status') == 'ok' and data.get('stream', {}).get('url'):
                    return data['stream']['url']
        except Exception:
            pass

        # 3. Local disk cache
        try:
            cache_file = os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "active_streams.json")
            if os.path.isfile(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    disk_cache = json.load(f)
                if video_id in disk_cache and disk_cache[video_id].get("url"):
                    return disk_cache[video_id]["url"]
        except Exception:
            pass

        return None

    def _real_extract(self, url):
        video_id = self._match_id(url)

        # 1. Check if direct M3U8 stream manifest is in clipboard or cache
        cached_m3u8 = self._get_cached_m3u8(video_id)
        if cached_m3u8:
            self.to_screen(f'[hanime] Using stream manifest from browser companion / clipboard: {video_id}')
            formats = []
            if '.mp4' in cached_m3u8 and '.m3u8' not in cached_m3u8:
                formats = [{
                    'url': cached_m3u8,
                    'ext': 'mp4',
                    'format_id': 'direct-mp4',
                    'quality': 1080,
                }]
            else:
                try:
                    formats = self._extract_m3u8_formats(cached_m3u8, video_id, ext='mp4', m3u8_id='1080p', fatal=False)
                except Exception as e:
                    self.to_screen(f'[hanime] Intercepted stream unavailable ({e}), trying live extraction...')
            if formats:
                video_title = video_id.replace('-', ' ').title()
                return {
                    'id': video_id,
                    'title': video_title,
                    'formats': formats
                }

        try:
            page = self._download_webpage(url, video_id, fatal=False, headers={'User-Agent': USER_AGENT})
        except Exception:
            page = None       

        ssignature, stime = self._generate_credentials_local()
        payload = self._digest_token({
            'timestamp_unix': int(time.time()),
            'directive': 'htv_player_handshake',
            'slug': video_id,
        })

        # Auto-discover local cookie files
        cookie_header = None
        candidate_cookies = [
            os.path.join(os.environ.get("APPDATA", ""), "yt-dlp", "cookies.txt"),
            os.path.join(os.environ.get("APPDATA", ""), "mpv-config", "cookies", "hanime.tv.txt"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "mpv-config", "cookies.txt"),
            "cookies.txt",
        ]
        for cpath in candidate_cookies:
            if cpath and os.path.isfile(cpath):
                try:
                    c_items = []
                    with open(cpath, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if line.startswith('#') or not line.strip():
                                continue
                            parts = line.strip().split('\t')
                            if len(parts) >= 7 and ('hanime' in parts[0] or 'cloudflare' in parts[0] or 'cf' in parts[5].lower()):
                                c_domain = parts[0]
                                c_name = parts[5]
                                c_val = parts[6]
                                c_items.append(f"{c_name}={c_val}")
                                try:
                                    self._set_cookie(c_domain, c_name, c_val)
                                except Exception:
                                    pass
                    if c_items:
                        cookie_header = '; '.join(c_items)
                        break
                except Exception:
                    pass

        handshake_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://hanime.tv',
            'Referer': 'https://hanime.tv/',
            'User-Agent': USER_AGENT,
            'X-Csrf-Token': 'null',
            'X-Signature': ssignature,
            'X-Time': str(stime),
            'X-Signature-Version': 'web2'
        }
        if cookie_header:
            handshake_headers['Cookie'] = cookie_header

        manifest = None

        # 2. Try curl_cffi modern browser TLS impersonation if available
        if cffi_requests:
            try:
                resp = cffi_requests.post(
                    "https://auth.hanime.tv/api/v11/handshake",
                    headers=handshake_headers,
                    data=json.dumps({'token': payload}),
                    impersonate="chrome124",
                    timeout=15
                )
                if resp.status_code == 200:
                    xtoken = resp.headers.get('X-Token') or resp.headers.get('x-token')
                    if xtoken:
                        manifest = self._parse_token(xtoken)
            except Exception:
                pass

        # 3. Fallback to standard yt-dlp HTTP handle
        if not manifest:
            try:
                _, handle = self._download_webpage_handle(
                    "https://auth.hanime.tv/api/v11/handshake",
                    video_id,
                    headers=handshake_headers,
                    data=json.dumps({'token': payload}).encode('ascii'),
                    note='Downloading video manifest'
                )
                xtoken = handle.headers.get('X-Token') or handle.headers.get('x-token')
                if xtoken:
                    manifest = self._parse_token(xtoken)
            except Exception as exc:
                # Check one more time if browser captured stream during request
                stream = self._get_cached_m3u8(video_id)
                if stream:
                    if '.mp4' in stream and '.m3u8' not in stream:
                        formats = [{
                            'url': stream,
                            'ext': 'mp4',
                            'format_id': 'direct-mp4',
                            'quality': 1080,
                        }]
                    else:
                        formats = self._extract_m3u8_formats(stream, video_id, ext='mp4', m3u8_id='1080p', fatal=False)
                    if formats:
                        return {
                            'id': video_id,
                            'title': video_id.replace('-', ' ').title(),
                            'formats': formats
                        }

                if '403' in str(exc) or 'Forbidden' in str(exc):
                    self.to_screen(f'[hanime] Cloudflare challenge detected. Engaging FlareSolverr automated solver...')
                    solution = _solve_via_flaresolverr(url)
                    if solution and solution.get('cookie_str'):
                        self.to_screen(f'[hanime] Successfully bypassed Cloudflare Turnstile via FlareSolverr!')
                        handshake_headers['Cookie'] = solution['cookie_str']
                        if solution.get('user_agent'):
                            handshake_headers['User-Agent'] = solution['user_agent']

                        # Propagate cookies to yt-dlp cookiejar
                        if solution.get('cookies'):
                            for c in solution['cookies']:
                                try:
                                    self._set_cookie(c.get('domain', '.hanime.tv'), c.get('name', ''), c.get('value', ''))
                                except Exception:
                                    pass

                        if cffi_requests:
                            try:
                                resp = cffi_requests.post(
                                    "https://auth.hanime.tv/api/v11/handshake",
                                    headers=handshake_headers,
                                    data=json.dumps({'token': payload}),
                                    impersonate="chrome124",
                                    timeout=15
                                )
                                if resp.status_code == 200:
                                    xt = resp.headers.get('X-Token') or resp.headers.get('x-token')
                                    if xt:
                                        manifest = self._parse_token(xt)
                            except Exception as e_cffi:
                                self.to_screen(f'[hanime] FlareSolverr cffi handshake notice: {e_cffi}')

                        if not manifest:
                            try:
                                req = urllib.request.Request(
                                    "https://auth.hanime.tv/api/v11/handshake",
                                    data=json.dumps({'token': payload}).encode('ascii'),
                                    headers=handshake_headers,
                                    method='POST'
                                )
                                with urllib.request.urlopen(req, timeout=15) as r2:
                                    xt = r2.headers.get('X-Token') or r2.headers.get('x-token')
                                    if xt:
                                        manifest = self._parse_token(xt)
                            except Exception as e2:
                                self.to_screen(f'[hanime] FlareSolverr clearance handshake notice: {e2}')

                    if not manifest:
                        raise ExtractorError(
                            f'Cloudflare Turnstile challenge active on hanime.tv (HTTP 403 Forbidden).\n'
                            f'Plug & Play Auto-Fix:\n'
                            f'1. Launch FlareSolverr (C:\\Tools\\FlareSolverr\\flaresolverr.exe) or open video once in Helium:\n'
                            f'   {url}\n'
                            f'2. The MPV Companion extension & userscript will automatically sync the fresh clearance\n'
                            f'   and stream manifest to yt-dlp / MPV in real time (zero manual export needed!).\n'
                            f'3. Or click "🎬 Play in MPV" or "⚡ Turbo Download" on the floating player pill.',
                            expected=True
                        )
                else:
                    raise

        if not manifest:
            raise ExtractorError('No X-Token found in response headers from auth.hanime.tv. Cloudflare challenge or auth error.', expected=True)

        cdn_headers = {
            'User-Agent': handshake_headers.get('User-Agent', USER_AGENT),
            'Referer': 'https://hanime.tv/',
            'Origin': 'https://hanime.tv',
        }
        if 'Cookie' in handshake_headers:
            cdn_headers['Cookie'] = handshake_headers['Cookie']

        formats = []
        for source in manifest.get('sources', []):
            if source.get('kind') == 'normal' and source.get('src'):
                src_url = urljoin('https://hanime.tv', source['src'])
                if '.m3u8' in src_url or '/hls/' in src_url:
                    result = self._extract_m3u8_formats(
                        src_url, video_id, ext='mp4', m3u8_id=source.get('label', 'default'),
                        headers=cdn_headers, fatal=False
                    )
                    for f in (result or []):
                        f.setdefault('http_headers', {}).update(cdn_headers)
                    if result:
                        formats.extend(result)
                elif '.mp4' in src_url:
                    formats.append({
                        'url': src_url,
                        'ext': 'mp4',
                        'format_id': source.get('label', 'direct-mp4'),
                        'http_headers': cdn_headers,
                    })

        has_1080p_locked = any(s.get('height') == 1080 and not s.get('src') for s in manifest.get('sources', []))
        if has_1080p_locked:
            self.to_screen('Note: 1080p is locked to Hanime.tv Premium members (server returned empty stream). Highest free stream is 720p.')

        top_headers = {
            'User-Agent': handshake_headers.get('User-Agent', USER_AGENT),
            'Referer': 'https://hanime.tv/',
            'Origin': 'https://hanime.tv',
        }

        video_title = (self._html_search_regex(r'<h1[^>]+?>([^<]+)', page, 'Video title', default=None) if page else None) or video_id.replace('-', ' ').title()
        return {
            'id': video_id,
            'title': video_title,
            'formats': formats,
            'http_headers': top_headers,
        }
