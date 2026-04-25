import re
import json
from urllib.parse import urlparse
import requests
from scraper import BROWSER_HEADERS, categorize_resource, get_extension, extract_filename

BILIBILI_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://www.bilibili.com',
    'Origin': 'https://www.bilibili.com',
}

BILIBILI_QUALITY_MAP = {
    120: '4K', 116: '1080P60', 112: '1080P高码率',
    80: '1080P', 74: '720P60', 64: '720P',
    48: '720P', 32: '480P', 16: '360P',
}

BILIBILI_AUDIO_QUALITY_MAP = {
    30251: 'Hi-Res', 30280: '高品质', 30232: '中品质', 30216: '低品质',
}

BILIBILI_CODEC_MAP = {
    7: 'H.264', 12: 'H.265', 13: 'AV1',
}


class BilibiliExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        return 'bilibili.com' in host or 'b23.tv' in host

    def _build_headers(self):
        headers = dict(BILIBILI_HEADERS)
        if self.cookies.get('SESSDATA'):
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
        return headers

    def extract(self, url, html=''):
        resources = []

        bvid, page_num = self._parse_url(url)
        if not bvid:
            return resources

        video_info = self._get_video_info(bvid)
        if not video_info:
            playinfo = self._parse_playinfo_from_html(html)
            if playinfo:
                return self._extract_from_playinfo(playinfo, 'video')
            return resources

        title = video_info.get('title', bvid)
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        aid = video_info.get('aid')
        cid = None
        pages = video_info.get('pages', [])
        if pages:
            idx = min(page_num - 1, len(pages) - 1)
            cid = pages[idx].get('cid')
            page_title = pages[idx].get('part', '')
            if page_title and len(pages) > 1:
                safe_title += '_' + re.sub(r'[<>:"/\\|?*]', '_', page_title)
        if not cid:
            cid = video_info.get('cid')

        dash_resources = self._get_dash_streams(aid, cid, safe_title)
        if dash_resources:
            resources.extend(dash_resources)
        else:
            nondash_resources = self._get_nondash_streams(aid, cid, safe_title)
            resources.extend(nondash_resources)

        for pic in video_info.get('pages', [{}])[0].get('metas', []):
            pic_url = pic.get('image_url', '')
            if pic_url and pic_url not in [r['url'] for r in resources]:
                resources.append({
                    'url': pic_url,
                    'name': f'{safe_title}_封面.jpg',
                    'category': 'image',
                    'extension': '.jpg',
                })

        return resources

    def _parse_url(self, url):
        bvid_match = re.search(r'/video/(BV[\w]+)', url)
        if not bvid_match:
            return None, 1
        bvid = bvid_match.group(1)
        parsed = urlparse(url)
        page_match = re.search(r'[?&]p=(\d+)', parsed.query)
        page_num = int(page_match.group(1)) if page_match else 1
        return bvid, page_num

    def _get_video_info(self, bvid):
        try:
            resp = requests.get(
                'https://api.bilibili.com/x/web-interface/view',
                params={'bvid': bvid},
                headers=self._build_headers(),
                cookies=self.cookies,
                timeout=15,
            )
            data = resp.json()
            if data.get('code') == 0:
                return data['data']
        except Exception:
            pass
        return None

    def _get_dash_streams(self, aid, cid, title):
        try:
            resp = requests.get(
                'https://api.bilibili.com/x/player/playurl',
                params={
                    'avid': aid,
                    'cid': cid,
                    'qn': 127,
                    'fnval': 16,
                    'fourk': 1,
                },
                headers=self._build_headers(),
                cookies=self.cookies,
                timeout=15,
            )
            data = resp.json()
            if data.get('code') != 0:
                return []

            dash = data.get('data', {}).get('dash', {})
            if not dash:
                return []

            return self._extract_from_dash(dash, title)
        except Exception:
            return []

    def _extract_from_dash(self, dash, title):
        resources = []
        dl_headers = self._build_headers()
        seen_video = set()
        for video in dash.get('video', []):
            quality = video.get('id', 0)
            codec_id = video.get('codecid', 7)
            q_label = BILIBILI_QUALITY_MAP.get(quality, f'{quality}P')
            c_label = BILIBILI_CODEC_MAP.get(codec_id, f'编码{codec_id}')
            key = (quality, codec_id)
            if key in seen_video:
                continue
            seen_video.add(key)

            url = video.get('baseUrl', '')
            if not url and video.get('backupUrl'):
                url = video['backupUrl'][0] if isinstance(video['backupUrl'], list) else video['backupUrl']
            if not url:
                continue

            resources.append({
                'url': url,
                'name': f'{title}_视频流_{q_label}_{c_label}.mp4',
                'category': 'video',
                'extension': '.mp4',
                'headers': dl_headers,
            })

        seen_audio = set()
        for audio in dash.get('audio', []):
            quality = audio.get('id', 0)
            q_label = BILIBILI_AUDIO_QUALITY_MAP.get(quality, f'品质{quality}')
            if quality in seen_audio:
                continue
            seen_audio.add(quality)

            url = audio.get('baseUrl', '')
            if not url and audio.get('backupUrl'):
                url = audio['backupUrl'][0] if isinstance(audio['backupUrl'], list) else audio['backupUrl']
            if not url:
                continue

            resources.append({
                'url': url,
                'name': f'{title}_音频流_{q_label}.m4a',
                'category': 'audio',
                'extension': '.m4a',
                'headers': dl_headers,
            })

        dolby = dash.get('dolby', {})
        if dolby and dolby.get('audio'):
            for audio in dolby['audio']:
                url = audio.get('baseUrl', '')
                if url:
                    resources.append({
                        'url': url,
                        'name': f'{title}_音频流_杜比音效.m4a',
                        'category': 'audio',
                        'extension': '.m4a',
                        'headers': dl_headers,
                    })

        return resources

    def _get_nondash_streams(self, aid, cid, title):
        for qn in [32, 16]:
            try:
                resp = requests.get(
                    'https://api.bilibili.com/x/player/playurl',
                    params={
                        'avid': aid,
                        'cid': cid,
                        'qn': qn,
                        'fnval': 0,
                    },
                    headers=self._build_headers(),
                    cookies=self.cookies,
                    timeout=15,
                )
                data = resp.json()
                if data.get('code') != 0:
                    continue

                durl = data.get('data', {}).get('durl', [])
                q_label = BILIBILI_QUALITY_MAP.get(qn, f'{qn}P')
                dl_headers = self._build_headers()
                resources = []
                for idx, segment in enumerate(durl):
                    url = segment.get('url', '')
                    if not url:
                        continue
                    suffix = f'_分段{idx + 1}' if len(durl) > 1 else ''
                    ext = '.mp4' if '.mp4' in url else '.flv'
                    resources.append({
                        'url': url,
                        'name': f'{title}_合并_{q_label}{suffix}{ext}',
                        'category': 'video',
                        'extension': ext,
                        'headers': dl_headers,
                    })
                if resources:
                    return resources
            except Exception:
                continue
        return []

    def _parse_playinfo_from_html(self, html):
        if not html:
            return None
        match = re.search(r'window\.__playinfo__\s*=\s*(\{.+?\})\s*</script>', html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_playinfo(self, playinfo, title_fallback):
        dash = playinfo.get('data', {}).get('dash', {})
        if dash:
            return self._extract_from_dash(dash, title_fallback)
        return []


XHS_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://www.xiaohongshu.com',
    'Origin': 'https://www.xiaohongshu.com',
}

XHS_IMAGE_SCENE_PRIORITY = ['WB_DFT', 'WB_PRV']


class XhsExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def _build_headers(self):
        headers = dict(XHS_HEADERS)
        if self.cookies:
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
        return headers

    def match(self, url):
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        return 'xiaohongshu.com' in host or 'xhslink.com' in host

    def extract(self, url, html=''):
        resources = []

        note_id = self._parse_url(url)
        if not note_id:
            return resources

        initial_state = self._parse_initial_state(html)
        notes_data = None

        if initial_state:
            notes_data = self._get_note_from_state(initial_state, note_id)

        if not notes_data:
            notes_data = self._fetch_note_api(note_id)

        if not notes_data:
            return resources

        note = notes_data.get('note', notes_data)
        title = note.get('title', note_id)
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title) if title else note_id
        note_type = note.get('type', 'normal')

        if note_type == 'video':
            video_resources = self._extract_video(note, safe_title)
            resources.extend(video_resources)

        image_resources = self._extract_images(note, safe_title)
        resources.extend(image_resources)

        return resources

    def _parse_url(self, url):
        match = re.search(r'/explore/([a-f0-9]+)', url)
        if match:
            return match.group(1)
        match = re.search(r'/discovery/item/([a-f0-9]+)', url)
        if match:
            return match.group(1)
        match = re.search(r'/note/([a-f0-9]+)', url)
        if match:
            return match.group(1)
        return None

    def _parse_initial_state(self, html):
        if not html:
            return None
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*\{', html)
        if not match:
            return None

        start = match.end() - 1
        end = html.find('</script>', start)
        if end == -1:
            return None

        raw = html[start:end].strip().rstrip(';').strip()
        raw = re.sub(r'\bundefined\b', 'null', raw)

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None

    def _get_note_from_state(self, state, note_id):
        try:
            note_map = state.get('note', {}).get('noteDetailMap', {})
            if note_id in note_map:
                return note_map[note_id]
            for nid, ndata in note_map.items():
                if isinstance(ndata, dict):
                    return ndata
        except Exception:
            pass
        return None

    def _fetch_note_api(self, note_id):
        return None

    def _extract_images(self, note, title):
        resources = []
        seen_urls = set()
        image_list = note.get('imageList', [])

        for idx, img in enumerate(image_list):
            best_url = self._pick_best_image_url(img)
            if not best_url or best_url in seen_urls:
                continue
            seen_urls.add(best_url)

            url = self._normalize_image_url(best_url)

            is_live = img.get('livePhoto', False)
            suffix = f'_LivePhoto' if is_live else ''

            ext = '.jpg'
            if '!nd_dft_wlteh_webp' in url or '!nd_prv_wlteh_webp' in url:
                ext = '.webp'
            elif '.png' in url.split('!')[0]:
                ext = '.png'

            resources.append({
                'url': url,
                'name': f'{title}_图片{idx + 1}{suffix}{ext}',
                'category': 'image',
                'extension': ext,
                'headers': self._build_headers(),
            })

        return resources

    def _pick_best_image_url(self, img):
        url_default = img.get('urlDefault', '') or img.get('url', '')
        if url_default:
            return url_default

        info_list = img.get('infoList', [])
        if not info_list:
            return ''

        for scene in XHS_IMAGE_SCENE_PRIORITY:
            for info in info_list:
                if info.get('imageScene') == scene and info.get('url'):
                    return info['url']

        for info in info_list:
            if info.get('url'):
                return info['url']

        return ''

    def _normalize_image_url(self, url):
        if url.startswith('http://'):
            url = 'https://' + url[len('http://'):]
        if 'xhscdn.com' in url and '!' not in url:
            url += '!nd_dft_wlteh_webp_3'
        return url

    def _extract_video(self, note, title):
        resources = []
        video = note.get('video', {})
        if not video:
            return resources

        consumer = video.get('consumer', {})
        origin_video_key = consumer.get('originVideoKey', '')
        if origin_video_key:
            video_url = self._normalize_video_url(origin_video_key)
            resources.append({
                'url': video_url,
                'name': f'{title}_视频_原画.mp4',
                'category': 'video',
                'extension': '.mp4',
                'headers': self._build_headers(),
            })

        video_key = video.get('key', '')
        if video_key and video_key != origin_video_key:
            video_url = self._normalize_video_url(video_key)
            resources.append({
                'url': video_url,
                'name': f'{title}_视频.mp4',
                'category': 'video',
                'extension': '.mp4',
                'headers': self._build_headers(),
            })

        url_default = video.get('urlDefault', '') or video.get('url', '')
        if url_default and url_default not in [r['url'] for r in resources]:
            if url_default.startswith('http://'):
                url_default = 'https://' + url_default[len('http://'):]
            resources.append({
                'url': url_default,
                'name': f'{title}_视频_默认.mp4',
                'category': 'video',
                'extension': '.mp4',
                'headers': self._build_headers(),
            })

        return resources

    def _normalize_video_url(self, key):
        if key.startswith('http'):
            return key
        return f'https://sns-video-al.xhscdn.com/{key}'


def extract_og_media(html):
    from bs4 import BeautifulSoup
    resources = []
    soup = BeautifulSoup(html, 'lxml')

    for prop in ['og:video', 'og:video:url', 'og:video:secure_url']:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            url = tag['content']
            resources.append({
                'url': url,
                'name': extract_filename(url) or 'video.mp4',
                'category': 'video',
                'extension': get_extension(url) or '.mp4',
            })
            break

    for prop in ['og:audio', 'og:audio:url', 'og:audio:secure_url']:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            url = tag['content']
            resources.append({
                'url': url,
                'name': extract_filename(url) or 'audio.mp3',
                'category': 'audio',
                'extension': get_extension(url) or '.mp3',
            })
            break

    return resources


def extract_jsonld_media(html):
    from bs4 import BeautifulSoup
    resources = []
    soup = BeautifulSoup(html, 'lxml')

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            content_url = item.get('contentUrl')
            if content_url:
                resources.append({
                    'url': content_url,
                    'name': extract_filename(content_url) or 'media',
                    'category': categorize_resource(content_url),
                    'extension': get_extension(content_url),
                })
            for embed in item.get('embedUrl', []):
                if embed:
                    resources.append({
                        'url': embed,
                        'name': extract_filename(embed) or 'embedded_media',
                        'category': categorize_resource(embed),
                        'extension': get_extension(embed),
                    })
    return resources


def extract_embedded_js_media(html):
    resources = []
    seen = set()

    media_url_patterns = [
        r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.flv[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.webm[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.mp3[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.wav[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.ogg[^\s"\'<>\\]*)',
        r'(https?://[^\s"\'<>\\]+\.aac[^\s"\'<>\\]*)',
    ]

    for pattern in media_url_patterns:
        for match in re.findall(pattern, html):
            url = match.rstrip('"\'),;]').rstrip('\\')
            if 'bilivideo.com' in url:
                continue
            if url in seen:
                continue
            if len(url) < 15:
                continue
            seen.add(url)
            resources.append({
                'url': url,
                'name': extract_filename(url),
                'category': categorize_resource(url),
                'extension': get_extension(url),
            })

    return resources


EXTRACTORS = []


def run_extractors(url, html='', cookies=None):
    all_resources = []
    seen_urls = set()

    cookie_dict = cookies or {}
    extractors = [BilibiliExtractor(cookies=cookie_dict), XhsExtractor(cookies=cookie_dict)]

    for extractor in extractors:
        if extractor.match(url):
            try:
                extracted = extractor.extract(url, html)
                for r in extracted:
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        all_resources.append(r)
            except Exception:
                pass

    if html:
        for extractor_fn in [extract_og_media, extract_jsonld_media, extract_embedded_js_media]:
            try:
                extracted = extractor_fn(html)
                for r in extracted:
                    if r['url'] not in seen_urls:
                        seen_urls.add(r['url'])
                        all_resources.append(r)
            except Exception:
                pass

    return all_resources
