import json
import time

from base64 import urlsafe_b64encode, urlsafe_b64decode

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Hash import SHA256
    from Cryptodome.Random import get_random_bytes
except ImportError:
    from Crypto.Cipher import AES
    from Crypto.Hash import SHA256
    from Crypto.Random import get_random_bytes

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
            PREFERRED_BROWSERS = ("brave", "chrome", "edge", "firefox")
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

    # This is not an AEAD scheme as much as it is a method of obscuring messages as the KEY and TAG for AES-256 GCM are known
    # beforehand. Note that, IV could be safely transmitted in the public without breaching the security.
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

    # Based on @barely-sad-one's code. This was perhaps reverse-engineered from the WASM code with some form of LLM assistance,
    # but it is not disclosed in the pull-request because yt-dlp has a ban on LLMs.
    @classmethod
    def _generate_credentials_local(cls):
        ts = int(time.time())
        digest = SHA256.new(f'{ts},Xkdi29,https://hanime.tv,mn2,{ts}'.encode('utf-8')).hexdigest()
        return digest, ts

    def _real_extract(self, url):
        video_id = self._match_id(url)
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
        _, handle = self._download_webpage_handle("https://auth.hanime.tv/api/v11/handshake", video_id,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://hanime.tv',
                'Referer': 'https://hanime.tv/',
                'User-Agent': USER_AGENT,
                'X-Csrf-Token': 'null',
                'X-Signature': ssignature,
                'X-Time': str(stime),
                'X-Signature-Version': 'web2'
            },
            data=json.dumps({'token': payload}).encode('ascii'),
            note='Downloading video manifest')

        # Manifest is transmitted in headers to confuse scrapers; whether or not it is optimal is not important.
        xtoken = handle.headers.get('X-Token') or handle.headers.get('x-token')
        if not xtoken:
            raise ExtractorError('No X-Token found in response headers from auth.hanime.tv. Cloudflare challenge or auth error.', expected=True)
        manifest = self._parse_token(xtoken)
        formats = []

        for source in manifest['sources']:
            # NOTE Premium streams are not supported and will not be supported in future.
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
