import os
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


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'


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
        """Query local MPV sync daemon and active streams file for intercepted M3U8 manifest."""
        # 1. Local HTTP Daemon
        try:
            req = urllib.request.Request(f'http://127.0.0.1:8765/stream?slug={video_id}')
            with urllib.request.urlopen(req, timeout=1.0) as r:
                data = json.loads(r.read().decode('utf-8'))
                if data.get('status') == 'ok' and data.get('stream', {}).get('url'):
                    return data['stream']['url']
        except Exception:
            pass

        # 2. Local disk cache
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

        # 1. Check if direct M3U8 stream manifest was intercepted by browser companion
        cached_m3u8 = self._get_cached_m3u8(video_id)
        if cached_m3u8:
            self.to_screen(f'[hanime] Using intercepted high-speed stream manifest from browser companion: {video_id}')
            formats = self._extract_m3u8_formats(cached_m3u8, video_id, ext='mp4', m3u8_id='1080p')
            return {
                'id': video_id,
                'title': video_id.replace('-', ' ').title(),
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
                                c_items.append(f"{parts[5]}={parts[6]}")
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
                    formats = self._extract_m3u8_formats(stream, video_id, ext='mp4', m3u8_id='1080p')
                    return {
                        'id': video_id,
                        'title': video_id.replace('-', ' ').title(),
                        'formats': formats
                    }

                if '403' in str(exc) or 'Forbidden' in str(exc):
                    raise ExtractorError(
                        f'Cloudflare Turnstile challenge active on hanime.tv (HTTP 403 Forbidden).\n'
                        f'Plug & Play Auto-Fix:\n'
                        f'1. Open this video once in your browser (Helium / Brave / Chrome):\n'
                        f'   {url}\n'
                        f'2. The MPV Companion extension & userscript will automatically sync the fresh clearance\n'
                        f'   and stream manifest to yt-dlp / MPV in real time (zero manual export needed!).\n'
                        f'3. Or click "🎬 Play in MPV" or "⚡ Turbo Download" on the floating player pill.',
                        expected=True
                    )
                raise

        if not manifest:
            raise ExtractorError('No X-Token found in response headers from auth.hanime.tv. Cloudflare challenge or auth error.', expected=True)

        formats = []
        for source in manifest['sources']:
            if source['kind'] == 'normal':
                result = self._extract_m3u8_formats(
                    urljoin('https://hanime.tv', source['src']), video_id, ext='mp4', m3u8_id=source['label'])
                formats.extend(result)

        video_title = (self._html_search_regex(r'<h1[^>]+?>([^<]+)', page, 'Video title', default=None) if page else None) or video_id.replace('-', ' ').title()
        return {
            'id': video_id,
            'title': video_title,
            'formats': formats
        }
