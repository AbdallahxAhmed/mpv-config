import re
import urllib.parse
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import remove_end, remove_start, ExtractorError


class TubePerverzijaIE(InfoExtractor):
    IE_NAME = 'perverzija'
    _VALID_URL = r'https?://(?:www\.)?tube\.perverzija\.com/(?P<id>[a-zA-Z0-9_-]+)/?'
    _TESTS = [{
        'url': 'https://tube.perverzija.com/manyvids-xev-bellringer-hooker-sister-gives-blow-job-in-car/',
        'info_dict': {
            'id': 'manyvids-xev-bellringer-hooker-sister-gives-blow-job-in-car',
            'ext': 'mp4',
            'title': 'ManyVids - Xev Bellringer - Hooker Sister Gives Blow Job In Car',
        }
    }]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id, headers={'Referer': 'https://tube.perverzija.com/'})

        title = self._og_search_title(webpage, default=None)
        if not title:
            title = self._html_search_regex(r'<title>(.*?)</title>', webpage, 'title', default=video_id)
        title = remove_start(title, 'Watch ')
        title = remove_end(title, ' | Perverzija.com')
        title = remove_end(title, ' - Perverzija')

        # Find xtremestream iframe
        iframe_src = self._search_regex(
            r'<iframe[^>]+src=["\'](https?://[^"\']+/player/index\.php\?data=[^"\']+)["\']',
            webpage, 'iframe player', default=None
        )

        if not iframe_src:
            data_id = self._search_regex(r'data-folderid=["\']([^"\']+)["\']', webpage, 'folder id', default=None)
            subdomain = self._search_regex(r'data-xtremestream=["\']([^"\']+)["\']', webpage, 'subdomain', default=None)
            if data_id and subdomain:
                iframe_src = f"https://{subdomain}.xtremestream.xyz/player/index.php?data={data_id}"

        if not iframe_src:
            raise ExtractorError("Could not find video player iframe on page", expected=True)

        parsed_iframe = urllib.parse.urlparse(iframe_src)
        qs = urllib.parse.parse_qs(parsed_iframe.query)
        stream_data_id = qs.get('data', [None])[0]
        if not stream_data_id:
            raise ExtractorError("Could not parse data id from iframe player URL", expected=True)

        player_base = f"{parsed_iframe.scheme}://{parsed_iframe.netloc}"
        m3u8_url = f"{player_base}/player/xs1.php?data={stream_data_id}"

        stream_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': iframe_src,
            'Origin': player_base,
        }

        formats = self._extract_m3u8_formats(
            m3u8_url, video_id, ext='mp4', entry_protocol='m3u8_native',
            headers=stream_headers
        )

        # 2. Taxonomy / Metadata from item-tax-list
        tax_match = re.search(r'<div[^>]*class=["\'][^"\']*item-tax-list[^"\']*["\'][^>]*>(.*?)</div>\s*</div>', webpage, re.DOTALL | re.IGNORECASE)
        tax_section = tax_match.group(1) if tax_match else webpage

        studio_match = re.search(r'<strong>\s*Studio:\s*</strong>.*?href=["\'][^"\']*/studio/([^/\'"]+)/?["\'][^>]*>([^<]+)<', tax_section, re.DOTALL | re.IGNORECASE)
        studio = studio_match.group(2).strip() if studio_match else None

        stars_section = re.search(r'<strong>\s*Stars:\s*</strong>(.*?)(?:</div>|$)', tax_section, re.DOTALL | re.IGNORECASE)
        stars = re.findall(r'href=["\'][^"\']*/stars/[^/\'"]+/?["\'][^>]*>([^<]+)<', stars_section.group(1) if stars_section else "")

        tags_section = re.search(r'<strong>\s*Tags:\s*</strong>(.*?)(?:</div>|$)', tax_section, re.DOTALL | re.IGNORECASE)
        tags = re.findall(r'href=["\'][^"\']*/tag/[^/\'"]+/?["\'][^>]*>([^<]+)<', tags_section.group(1) if tags_section else "")

        thumbnail = self._og_search_thumbnail(webpage, default=None)
        description = self._og_search_description(webpage, default=None)

        # Duration (ISO 8601 like PT19M33S)
        duration_str = self._search_regex(r'["\']duration["\']\s*:\s*["\']([^"\']+)["\']', webpage, 'duration', default=None)
        duration = None
        if duration_str:
            from yt_dlp.utils import parse_duration
            duration = parse_duration(duration_str)

        return {
            'id': video_id,
            'title': title,
            'creator': studio,
            'uploader': studio,
            'cast': list(dict.fromkeys(stars)),
            'tags': list(dict.fromkeys(tags)),
            'duration': duration,
            'formats': formats,
            'thumbnail': thumbnail,
            'description': description,
            'http_headers': stream_headers,
        }

