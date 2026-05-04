import re
import json
from urllib.parse import urlparse, unquote, quote
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
BILIBILI_CODEC_MAP = {7: 'H.264', 12: 'H.265', 13: 'AV1'}


class BilibiliExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
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
                resources.append({'url': pic_url, 'name': f'{safe_title}_封面.jpg', 'category': 'image', 'extension': '.jpg'})
        return resources

    def _parse_url(self, url):
        m = re.search(r'/video/(BV[\w]+)', url)
        if not m:
            return None, 1
        parsed = urlparse(url)
        pm = re.search(r'[?&]p=(\d+)', parsed.query)
        return m.group(1), int(pm.group(1)) if pm else 1

    def _get_video_info(self, bvid):
        try:
            resp = requests.get('https://api.bilibili.com/x/web-interface/view', params={'bvid': bvid}, headers=self._build_headers(), cookies=self.cookies, timeout=15)
            data = resp.json()
            if data.get('code') == 0:
                return data['data']
        except Exception:
            pass
        return None

    def _get_dash_streams(self, aid, cid, title):
        try:
            resp = requests.get('https://api.bilibili.com/x/player/playurl', params={'avid': aid, 'cid': cid, 'qn': 127, 'fnval': 16, 'fourk': 1}, headers=self._build_headers(), cookies=self.cookies, timeout=15)
            data = resp.json()
            if data.get('code') != 0:
                return []
            dash = data.get('data', {}).get('dash', {})
            return self._extract_from_dash(dash, title) if dash else []
        except Exception:
            return []

    def _extract_from_dash(self, dash, title):
        resources = []
        dl_headers = self._build_headers()
        seen_video = set()
        for video in dash.get('video', []):
            quality, codec_id = video.get('id', 0), video.get('codecid', 7)
            key = (quality, codec_id)
            if key in seen_video:
                continue
            seen_video.add(key)
            url = video.get('baseUrl', '') or (video['backupUrl'][0] if isinstance(video.get('backupUrl'), list) else video.get('backupUrl', ''))
            if url:
                resources.append({'url': url, 'name': f'{title}_视频流_{BILIBILI_QUALITY_MAP.get(quality, f"{quality}P")}_{BILIBILI_CODEC_MAP.get(codec_id, f"编码{codec_id}")}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        seen_audio = set()
        for audio in dash.get('audio', []):
            quality = audio.get('id', 0)
            if quality in seen_audio:
                continue
            seen_audio.add(quality)
            url = audio.get('baseUrl', '') or (audio['backupUrl'][0] if isinstance(audio.get('backupUrl'), list) else audio.get('backupUrl', ''))
            if url:
                resources.append({'url': url, 'name': f'{title}_音频流_{BILIBILI_AUDIO_QUALITY_MAP.get(quality, f"品质{quality}")}.m4a', 'category': 'audio', 'extension': '.m4a', 'headers': dl_headers})
        for audio in (dash.get('dolby', {}) or {}).get('audio', []) or []:
            url = audio.get('baseUrl', '')
            if url:
                resources.append({'url': url, 'name': f'{title}_音频流_杜比音效.m4a', 'category': 'audio', 'extension': '.m4a', 'headers': dl_headers})
        return resources

    def _get_nondash_streams(self, aid, cid, title):
        for qn in [32, 16]:
            try:
                resp = requests.get('https://api.bilibili.com/x/player/playurl', params={'avid': aid, 'cid': cid, 'qn': qn, 'fnval': 0}, headers=self._build_headers(), cookies=self.cookies, timeout=15)
                data = resp.json()
                if data.get('code') != 0:
                    continue
                durl = data.get('data', {}).get('durl', [])
                dl_headers = self._build_headers()
                resources = []
                for idx, segment in enumerate(durl):
                    url = segment.get('url', '')
                    if url:
                        suffix = f'_分段{idx + 1}' if len(durl) > 1 else ''
                        ext = '.mp4' if '.mp4' in url else '.flv'
                        resources.append({'url': url, 'name': f'{title}_合并_{BILIBILI_QUALITY_MAP.get(qn, f"{qn}P")}{suffix}{ext}', 'category': 'video', 'extension': ext, 'headers': dl_headers})
                if resources:
                    return resources
            except Exception:
                continue
        return []

    def _parse_playinfo_from_html(self, html):
        if not html:
            return None
        m = re.search(r'window\.__playinfo__\s*=\s*(\{.+?\})\s*</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_playinfo(self, playinfo, title_fallback):
        dash = playinfo.get('data', {}).get('dash', {})
        return self._extract_from_dash(dash, title_fallback) if dash else []


XHS_HEADERS = {**BROWSER_HEADERS, 'Referer': 'https://www.xiaohongshu.com', 'Origin': 'https://www.xiaohongshu.com'}
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
        host = (urlparse(url).hostname or '').lower()
        return 'xiaohongshu.com' in host or 'xhslink.com' in host

    def extract(self, url, html=''):
        resources = []
        note_id = self._parse_url(url)
        if not note_id:
            return resources
        initial_state = self._parse_initial_state(html)
        notes_data = self._get_note_from_state(initial_state, note_id) if initial_state else None
        if not notes_data:
            return resources
        note = notes_data.get('note', notes_data)
        title = note.get('title', note_id)
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title) if title else note_id
        if note.get('type') == 'video':
            resources.extend(self._extract_video(note, safe_title))
        resources.extend(self._extract_images(note, safe_title))
        return resources

    def _parse_url(self, url):
        for pat in [r'/explore/([a-f0-9]+)', r'/discovery/item/([a-f0-9]+)', r'/note/([a-f0-9]+)']:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return None

    def _parse_initial_state(self, html):
        if not html:
            return None
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*\{', html)
        if not m:
            return None
        start = m.end() - 1
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
            for ndata in note_map.values():
                if isinstance(ndata, dict):
                    return ndata
        except Exception:
            pass
        return None

    def _extract_images(self, note, title):
        resources = []
        seen_urls = set()
        for idx, img in enumerate(note.get('imageList', [])):
            best_url = img.get('urlDefault', '') or img.get('url', '')
            if not best_url:
                for scene in XHS_IMAGE_SCENE_PRIORITY:
                    for info in img.get('infoList', []):
                        if info.get('imageScene') == scene and info.get('url'):
                            best_url = info['url']
                            break
                    if best_url:
                        break
                if not best_url:
                    for info in img.get('infoList', []):
                        if info.get('url'):
                            best_url = info['url']
                            break
            if not best_url or best_url in seen_urls:
                continue
            seen_urls.add(best_url)
            url = best_url.replace('http://', 'https://')
            if 'xhscdn.com' in url and '!' not in url:
                url += '!nd_dft_wlteh_webp_3'
            is_live = img.get('livePhoto', False)
            ext = '.webp' if '!nd_dft_wlteh' in url else ('.png' if '.png' in url.split('!')[0] else '.jpg')
            resources.append({'url': url, 'name': f'{title}_图片{idx + 1}{"_LivePhoto" if is_live else ""}{ext}', 'category': 'image', 'extension': ext, 'headers': self._build_headers()})
        return resources

    def _extract_video(self, note, title):
        resources = []
        video = note.get('video', {})
        if not video:
            return resources
        dl_headers = self._build_headers()
        for key, label in [('originVideoKey', '原画'), ('key', '')]:
            val = video.get(key, '') if key != 'originVideoKey' else video.get('consumer', {}).get('originVideoKey', '')
            if val:
                vurl = val if val.startswith('http') else f'https://sns-video-al.xhscdn.com/{val}'
                suffix = f'_{label}' if label else ''
                if vurl not in [r['url'] for r in resources]:
                    resources.append({'url': vurl, 'name': f'{title}_视频{suffix}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        url_default = video.get('urlDefault', '') or video.get('url', '')
        if url_default and url_default not in [r['url'] for r in resources]:
            resources.append({'url': url_default.replace('http://', 'https://'), 'name': f'{title}_视频_默认.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        return resources


WEIBO_HEADERS = {**BROWSER_HEADERS, 'Referer': 'https://weibo.com'}


class WeiboExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'weibo.com' in host or 'weibo.cn' in host

    def extract(self, url, html=''):
        resources = []
        if html:
            state = self._parse_render_data(html)
            if not state:
                state = self._parse_initial_state(html)
            if state:
                resources.extend(self._extract_from_state(state))
            resources.extend(self._extract_sinaimg_from_html(html))
            resources.extend(self._extract_fvideo_from_html(html))
        if not resources:
            weibo_id = self._parse_url(url)
            if weibo_id:
                api_data = self._fetch_mweibo_api(weibo_id)
                if api_data:
                    resources.extend(self._extract_from_mweibo(api_data))
        return self._dedup(resources)

    def _parse_url(self, url):
        m = re.search(r'/status/(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/detail/(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/(\d{10,})', url)
        if m:
            return m.group(1)
        return None

    def _fetch_mweibo_api(self, weibo_id):
        try:
            api_url = f'https://m.weibo.cn/statuses/show'
            headers = {**BROWSER_HEADERS, 'Referer': 'https://m.weibo.cn/'}
            if self.cookies:
                cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
                if cookie_str:
                    headers['Cookie'] = cookie_str
            resp = requests.get(api_url, params={'id': weibo_id}, headers=headers, timeout=15)
            data = resp.json()
            if data.get('ok') == 1:
                return data.get('data', {})
        except Exception:
            pass
        return None

    def _extract_from_mweibo(self, data):
        resources = []
        pic_ids = data.get('pic_ids', [])
        pic_infos = data.get('pic_infos', {})
        page_info = data.get('page_info', {})
        for pic_id in pic_ids:
            info = pic_infos.get(pic_id, {})
            for size in ['original', 'large', 'mw2000']:
                img_info = info.get(size, {})
                url = img_info.get('url', '')
                if url:
                    resources.append({'url': url, 'name': f'weibo_{pic_id}.jpg', 'category': 'image', 'extension': '.jpg', 'headers': WEIBO_HEADERS})
                    break
        media_info = page_info.get('media_info', {})
        video_url = media_info.get('stream_url_hd', '') or media_info.get('stream_url', '') or media_info.get('mp4_hd_url', '') or media_info.get('mp4_sd_url', '')
        if video_url:
            resources.append({'url': video_url, 'name': 'weibo_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': WEIBO_HEADERS})
        return resources

    def _parse_render_data(self, html):
        m = re.search(r'var\s+\$render_data\s*=\s*\[(\{.+?\})\]\s*;', html, re.DOTALL)
        if m:
            try:
                raw = m.group(1).replace('\\/', '/').replace('\\u002F', '/').replace('&amp;', '&')
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _parse_initial_state(self, html):
        m = re.search(r'window\.\$initial_state\s*=\s*(\{.+?\})\s*;', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_state(self, state):
        resources = []
        status = None
        for key_path in [['status'], ['statusMap', list(state.get('statusMap', {}).keys())[0]] if state.get('statusMap') else []]:
            try:
                obj = state
                for k in key_path:
                    obj = obj[k]
                status = obj
                break
            except (KeyError, TypeError, IndexError):
                pass
        if not status:
            return resources
        text = json.dumps(status, ensure_ascii=False)
        pics = re.findall(r'"pic_id"\s*:\s*"(\w+)"', text)
        pic_infos = status.get('pic_infos', {}) if isinstance(status, dict) else {}
        for pic_id, info in pic_infos.items():
            for size in ['original', 'large', 'mw2000']:
                img_info = info.get(size, {})
                url = img_info.get('url', '')
                if url:
                    resources.append({'url': url, 'name': f'weibo_{pic_id}.jpg', 'category': 'image', 'extension': '.jpg', 'headers': WEIBO_HEADERS})
                    break
        page_info = status.get('page_info', {}) if isinstance(status, dict) else {}
        media_info = page_info.get('media_info', {})
        video_url = media_info.get('stream_url_hd', '') or media_info.get('stream_url', '') or media_info.get('mp4_hd_url', '') or media_info.get('mp4_sd_url', '')
        if video_url:
            resources.append({'url': video_url, 'name': 'weibo_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': WEIBO_HEADERS})
        return resources

    def _extract_sinaimg_from_html(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://[a-z]\d+\.sinaimg\.cn/[^\s"\'<>\\]+)', html)
        for url in urls:
            url = url.replace('\\/', '/').rstrip('"\'),;]').rstrip('\\')
            original_url = re.sub(r'/[a-z]+\d+/', '/large/', url)
            if original_url not in seen:
                seen.add(original_url)
                fname = original_url.split('/')[-1].split('?')[0] or 'weibo_img.jpg'
                resources.append({'url': original_url, 'name': fname, 'category': 'image', 'extension': '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg', 'headers': WEIBO_HEADERS})
        return resources

    def _extract_fvideo_from_html(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'"(https?://f\.video\.weibocdn\.com/[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*)', html)
        for url in urls:
            url = url.replace('\\/', '/').rstrip('"\'),;]').rstrip('\\')
            if url not in seen:
                seen.add(url)
                resources.append({'url': url, 'name': 'weibo_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': WEIBO_HEADERS})
        return resources

    def _dedup(self, resources):
        seen = set()
        result = []
        for r in resources:
            if r['url'] not in seen:
                seen.add(r['url'])
                result.append(r)
        return result


class DouyinExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'douyin.com' in host or 'iesdouyin.com' in host

    def extract(self, url, html=''):
        resources = []
        aweme_id = self._parse_url(url)
        if aweme_id:
            resources = self._try_all_methods(aweme_id, url, html)
        if not resources:
            resources = self._try_all_methods(None, url, html)
        return resources

    def _try_all_methods(self, aweme_id, url, html):
        dl_headers = {**BROWSER_HEADERS, 'Referer': 'https://www.douyin.com/'}
        strategies = [
            ('community_api', lambda: self._try_community_api(aweme_id or self._parse_url_fallback(url), dl_headers)),
            ('community_api2', lambda: self._try_community_api2(aweme_id or self._parse_url_fallback(url), url, dl_headers)),
            ('playwright', lambda: self._try_playwright(url, dl_headers)),
            ('official_api', lambda: self._try_official_api(aweme_id or self._parse_url_fallback(url), dl_headers)),
            ('router_data', lambda: self._extract_from_state_router(html, dl_headers)),
            ('ssr_html', lambda: self._extract_ssr_html(html)),
        ]
        for name, fn in strategies:
            try:
                result = fn()
                if result:
                    return result
            except Exception:
                continue
        return self._extract_og_media(html)

    def _parse_url(self, url):
        m = re.search(r'/video/(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/note/(\d+)', url)
        if m:
            return m.group(1)
        return None

    def _parse_url_fallback(self, url):
        for pat in [r'/video/(\d+)', r'/note/(\d+)', r'/(\d{15,})']:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return ''

    # ---- Strategy 1: Community API (tikwm.com) ----
    def _try_community_api(self, aweme_id, dl_headers):
        if not aweme_id:
            return []
        try:
            resp = requests.get('https://www.tikwm.com/api/', params={'url': aweme_id}, headers={**BROWSER_HEADERS, 'Referer': 'https://www.tikwm.com/'}, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get('code') != 0:
                return []
            return self._parse_community_data(data, dl_headers)
        except Exception:
            return []

    def _try_community_api2(self, aweme_id, original_url, dl_headers):
        try:
            target_url = original_url
            if 'v.douyin.com' in original_url:
                target_url = original_url
            elif aweme_id:
                target_url = f'https://www.douyin.com/video/{aweme_id}'
            resp = requests.get('https://www.tikwm.com/api/', params={'url': target_url}, headers={**BROWSER_HEADERS, 'Referer': 'https://www.tikwm.com/'}, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get('code') != 0:
                return []
            return self._parse_community_data(data, dl_headers)
        except Exception:
            return []

    def _parse_community_data(self, data, dl_headers):
        resources = []
        d = data.get('data', {})
        video_url = d.get('play') or d.get('hdplay') or d.get('wmplay') or d.get('download')
        if video_url:
            if video_url.startswith('//'):
                video_url = 'https:' + video_url
            title = d.get('title', 'douyin_video')[:50]
            safe = re.sub(r'[<>:"/\\|?*]', '_', title)
            resources.append({'url': video_url, 'name': f'{safe}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        cover = d.get('cover') or d.get('origin_cover')
        if cover:
            if cover.startswith('//'):
                cover = 'https:' + cover
            resources.append({'url': cover, 'name': 'douyin_cover.jpg', 'category': 'image', 'extension': '.jpg', 'headers': dl_headers})
        music = d.get('music') or d.get('music_info')
        if isinstance(music, dict):
            music_url = music.get('play_url') or music.get('play') or music.get('url')
            if music_url:
                if music_url.startswith('//'):
                    music_url = 'https:' + music_url
                music_name = music.get('title', 'douyin_music')[:50]
                ext = '.mp3' if '.mp3' in music_url else '.m4a'
                resources.append({'url': music_url, 'name': f'{music_name}{ext}', 'category': 'audio', 'extension': ext, 'headers': dl_headers})
        images = d.get('images') or []
        if isinstance(images, list):
            for i, img in enumerate(images):
                if isinstance(img, str):
                    resources.append({'url': img, 'name': f'douyin_img_{i+1}.jpeg', 'category': 'image', 'extension': '.jpeg', 'headers': dl_headers})
        return resources

    # ---- Strategy 2: Playwright browser automation ----
    def _try_playwright(self, url, dl_headers):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={'width': 1920, 'height': 1080})
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(3000)
                data = page.evaluate('() => { try { return window._ROUTER_DATA; } catch(e) { return null; } }')
                if data is None:
                    data = page.evaluate('() => { try { var s = document.getElementById("RENDER_DATA"); return s ? decodeURIComponent(s.textContent) : null; } catch(e) { return null; } }')
                    if data:
                        import json
                        data = json.loads(data)
                browser.close()
                if not data:
                    return []
                return self._extract_from_router(data, dl_headers)
        except Exception:
            return []

    def _extract_from_router(self, state, dl_headers):
        resources = []
        if isinstance(state, str):
            try:
                import json
                state = json.loads(state)
            except:
                return []
        d_str = json.dumps(state, ensure_ascii=False)
        video_urls = re.findall(r'(https?://[^\s"\'<>]+\.(?:mp4|mov|flv)[^\s"\'<>]*)', d_str)
        if not video_urls:
            video_urls = re.findall(r'"url_list"\s*:\s*\["([^"]+)"', d_str)
        if not video_urls:
            video_urls = re.findall(r'"playApi"\s*:\s*"([^"]+)"', d_str)
        if not video_urls:
            video_urls = re.findall(r'"play_addr".*?"url_list"\s*:\s*\["([^"]+)"', d_str)
        for i, vurl in enumerate(video_urls[:5]):
            vurl = vurl.replace('\\u002F', '/').replace('\\/', '/')
            if vurl.startswith('//'):
                vurl = 'https:' + vurl
            resources.append({'url': vurl, 'name': f'douyin_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        cover_urls = re.findall(r'(https?://[^\s"\'<>]+douyinpic[^\s"\'<>]*\.(?:jpg|jpeg|webp)[^\s"\'<>]*)', d_str)
        for i, curl in enumerate(cover_urls[:5]):
            curl = curl.replace('\\u002F', '/').replace('\\/', '/')
            if curl.startswith('//'):
                curl = 'https:' + curl
            ext = '.webp' if '.webp' in curl else '.jpg'
            resources.append({'url': curl, 'name': f'douyin_cover_{i + 1}{ext}', 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources

    # ---- Strategy 3: Official API (with cookies) ----
    def _try_official_api(self, aweme_id, dl_headers):
        if not aweme_id:
            return []
        api_data = self._fetch_aweme_detail(aweme_id)
        if api_data:
            return self._extract_from_official_api(api_data, dl_headers)
        return []

    def _fetch_aweme_detail(self, aweme_id):
        try:
            api_url = 'https://www.douyin.com/aweme/v1/web/aweme/detail/'
            params = {'aweme_id': aweme_id, 'aid': '6383', 'cookie_enabled': 'true'}
            headers = {**BROWSER_HEADERS, 'Referer': 'https://www.douyin.com/', 'Accept': 'application/json, text/plain, */*'}
            if self.cookies:
                cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
                if cookie_str:
                    headers['Cookie'] = cookie_str
            resp = requests.get(api_url, params=params, headers=headers, timeout=15)
            if not resp.text:
                return None
            data = resp.json()
            if data.get('status_code') == 0:
                return data.get('aweme_detail', {})
        except Exception:
            pass
        return None

    def _extract_from_official_api(self, aweme, dl_headers):
        resources = []
        video = aweme.get('video', {})
        play_addr = video.get('play_addr', {})
        url_list = play_addr.get('url_list', [])
        if url_list:
            vurl = url_list[0]
            if vurl.startswith('//'):
                vurl = 'https:' + vurl
            desc = aweme.get('desc', 'douyin_video')
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', desc)[:50]
            resources.append({'url': vurl, 'name': f'{safe_name}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        cover = video.get('cover', {})
        cover_urls = cover.get('url_list', [])
        if cover_urls:
            curl = cover_urls[0]
            if curl.startswith('//'):
                curl = 'https:' + curl
            resources.append({'url': curl, 'name': 'douyin_cover.jpg', 'category': 'image', 'extension': '.jpg', 'headers': dl_headers})
        images = aweme.get('images', [])
        for i, img in enumerate(images):
            url_list = img.get('url_list', [])
            if url_list:
                img_url = url_list[0]
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                resources.append({'url': img_url, 'name': f'douyin_image_{i+1}.jpeg', 'category': 'image', 'extension': '.jpeg', 'headers': dl_headers})
        return resources

    # ---- Strategy 4: Router data from HTML SSR ----
    def _extract_from_state_router(self, html, dl_headers):
        if not html or len(html) < 1000:
            return []
        state = self._parse_router_data(html)
        if not state:
            return []
        resources = []
        for key in state:
            if 'video' in key.lower() or 'note' in key.lower() or 'post' in key.lower():
                try:
                    data = state[key]
                    d_str = json.dumps(data, ensure_ascii=False)
                    for pattern in [r'"url_list"\s*:\s*\["([^"]+)"', r'"play_addr".*?"url_list"\s*:\s*\["([^"]+)"', r'"playApi"\s*:\s*"([^"]+)"']:
                        video_urls = re.findall(pattern, d_str)
                        for vurl in video_urls[:5]:
                            vurl = vurl.replace('\\u002F', '/').replace('\\/', '/')
                            if vurl.startswith('//'):
                                vurl = 'https:' + vurl
                            if vurl not in [r['url'] for r in resources]:
                                resources.append({'url': vurl, 'name': f'douyin_video_{len(resources) + 1}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
                        if video_urls:
                            break
                    cover_urls = re.findall(r'"cover".*?"url_list"\s*:\s*\["([^"]+)"', d_str)
                    for curl in cover_urls[:3]:
                        curl = curl.replace('\\u002F', '/').replace('\\/', '/')
                        if curl.startswith('//'):
                            curl = 'https:' + curl
                        resources.append({'url': curl, 'name': 'douyin_cover.jpg', 'category': 'image', 'extension': '.jpg', 'headers': dl_headers})
                except Exception:
                    pass
        return resources

    def _parse_router_data(self, html):
        m = re.search(r'window\._ROUTER_DATA\s*=\s*(\{.+?)\s*</script>', html, re.DOTALL)
        if m:
            try:
                raw = re.sub(r'\bundefined\b', 'null', m.group(1))
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # ---- Strategy 5: SSR HTML CDN patterns ----
    def _extract_ssr_html(self, html):
        if not html or len(html) < 1000:
            return []
        resources = []
        dl_headers = {**BROWSER_HEADERS, 'Referer': 'https://www.douyin.com/'}
        video_urls = re.findall(r'(https?://[^\s"\'<>]+douyinvod[^\s"\'<>]*\.mp4[^\s"\'<>]*)', html)
        for i, url in enumerate(video_urls[:5]):
            url = url.rstrip('"\'),;]').rstrip('\\')
            resources.append({'url': url, 'name': f'douyin_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        cover_urls = re.findall(r'(https?://[^\s"\'<>]+douyinpic[^\s"\'<>]*\.(?:jpg|jpeg|webp)[^\s"\'<>]*)', html)
        for i, url in enumerate(cover_urls[:5]):
            url = url.rstrip('"\'),;]').rstrip('\\')
            ext = '.webp' if '.webp' in url else '.jpg'
            resources.append({'url': url, 'name': f'douyin_cover_{i + 1}{ext}', 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources

    # ---- Fallback: og:meta ----
    def _extract_og_media(self, html):
        resources = []
        m = re.search(r'property=["\']og:video["\'].*?content=["\'](.*?)["\']', html)
        if m:
            resources.append({'url': m.group(1), 'name': 'douyin_video_og.mp4', 'category': 'video', 'extension': '.mp4'})
        m = re.search(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        if m:
            resources.append({'url': m.group(1), 'name': 'douyin_cover_og.jpg', 'category': 'image', 'extension': '.jpg'})
        return resources


class KuaishouExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'kuaishou.com' in host or 'gifshow.com' in host or 'kwai.com' in host

    def extract(self, url, html=''):
        resources = []
        state = self._parse_apollo_state(html)
        if state:
            resources.extend(self._extract_from_state(state))
        if not resources:
            resources.extend(self._extract_from_html(html))
        return resources

    def _parse_apollo_state(self, html):
        m = re.search(r'window\.__APOLLO_STATE__\s*=\s*', html)
        if not m:
            return None
        start = m.end()
        end = html.find('</script>', start)
        raw = html[start:end].strip().rstrip(';').strip()
        raw = re.sub(r'\bundefined\b', 'null', raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        try:
            decoder = json.JSONDecoder()
            obj, idx = decoder.raw_decode(raw)
            return obj
        except (json.JSONDecodeError, ValueError):
            pass
        for end_pos in range(len(raw) - 100, 0, -500):
            try:
                decoder = json.JSONDecoder()
                obj, idx = decoder.raw_decode(raw[:end_pos])
                return obj
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def _extract_from_state(self, state):
        resources = []
        dl_headers = {**BROWSER_HEADERS, 'Referer': 'https://www.kuaishou.com/'}
        dc = state.get('defaultClient', {})
        for key, val in dc.items():
            if not isinstance(val, dict):
                continue
            d_str = json.dumps(val, ensure_ascii=False)
            photo_url = val.get('photoUrl', '') or val.get('srcNoMark', '')
            if photo_url and '.mp4' in photo_url:
                resources.append({'url': photo_url, 'name': 'kuaishou_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
            poster_url = val.get('poster', '') or val.get('coverUrl', '')
            if poster_url:
                resources.append({'url': poster_url, 'name': 'kuaishou_cover.jpg', 'category': 'image', 'extension': '.jpg', 'headers': dl_headers})
            video_urls = re.findall(r'"(https?://[^\s"\'<>]*(?:kwai|kuaishou|ks\.cdn)[^\s"\'<>]*\.mp4[^\s"\'<>]*)"', d_str)
            for vurl in video_urls[:3]:
                vurl = vurl.replace('\\u002F', '/').replace('\\/', '/')
                if vurl not in [r['url'] for r in resources]:
                    resources.append({'url': vurl, 'name': 'kuaishou_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
            img_urls = re.findall(r'"(https?://[^\s"\'<>]*(?:kwai|kuaishou|ks\.cdn|yximgs)[^\s"\'<>]*\.(?:jpg|jpeg|png|webp))[^\s"\'<>]*"', d_str)
            for iurl in img_urls[:5]:
                iurl = iurl.replace('\\u002F', '/').replace('\\/', '/')
                if iurl not in [r['url'] for r in resources]:
                    ext = '.webp' if '.webp' in iurl else '.jpg'
                    resources.append({'url': iurl, 'name': f'kuaishou_img_{len(resources)}{ext}', 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources

    def _extract_from_html(self, html):
        resources = []
        dl_headers = {**BROWSER_HEADERS, 'Referer': 'https://www.kuaishou.com/'}
        video_urls = re.findall(r'"(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)"', html)
        for url in video_urls[:5]:
            url = url.replace('\\u002F', '/').replace('\\/', '/')
            resources.append({'url': url, 'name': 'kuaishou_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        poster_urls = re.findall(r'"poster"\s*:\s*"(https?://[^\s"\'<>]+\.(?:jpg|jpeg|webp)[^\s"\'<>]*)"', html)
        for url in poster_urls[:3]:
            url = url.replace('\\u002F', '/').replace('\\/', '/')
            ext = '.webp' if '.webp' in url else '.jpg'
            resources.append({'url': url, 'name': f'kuaishou_cover{ext}', 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources


class ZhihuExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def _build_headers(self):
        headers = {**BROWSER_HEADERS, 'Referer': 'https://www.zhihu.com/'}
        if self.cookies:
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
        return headers

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'zhihu.com' in host

    def extract(self, url, html=''):
        resources = []
        data = None
        if html:
            data = self._parse_initial_data(html)
        if not data:
            data = self._fetch_page_data(url)
        if data:
            resources.extend(self._extract_from_data(data))
        if html:
            resources.extend(self._extract_zhimg_from_html(html))
        return self._dedup(resources)

    def _parse_initial_data(self, html):
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?)\s*;?\s*</script>', html, re.DOTALL)
        if m:
            try:
                raw = re.sub(r'\bundefined\b', 'null', m.group(1))
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass
        m = re.search(r'window\.__NEXT_DATA__\s*=\s*(\{.+?)\s*</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _fetch_page_data(self, url):
        headers = self._build_headers()
        m = re.search(r'zhuanlan\.zhihu\.com/p/(\d+)', url)
        if m:
            try:
                api_url = f'https://zhuanlan.zhihu.com/api/articles/{m.group(1)}'
                resp = requests.get(api_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        m = re.search(r'zhihu\.com/question/(\d+)', url)
        if m:
            try:
                api_url = f'https://www.zhihu.com/api/v4/questions/{m.group(1)}/answers'
                resp = requests.get(api_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        return None

    def _extract_from_data(self, data):
        resources = []
        d_str = json.dumps(data, ensure_ascii=False)
        video_urls = re.findall(r'(https?://vd[^\s"\'<>]+\.mp4[^\s"\'<>]*)', d_str)
        for i, vurl in enumerate(video_urls[:5]):
            vurl = vurl.rstrip('"\'),;]').rstrip('\\')
            resources.append({'url': vurl, 'name': f'zhihu_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        img_urls = re.findall(r'(https?://[a-z]\d+\.zhimg\.com/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif))[^\s"\'<>]*', d_str)
        seen = set()
        for url in img_urls:
            if 'avatar' in url or 'chart' in url or url in seen:
                continue
            seen.add(url)
            fname = url.split('/')[-1] or 'zhihu_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        content = data.get('content', '') or data.get('excerpt', '')
        if content:
            content_imgs = re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', content)
            for url in content_imgs:
                if 'zhimg.com' in url and url not in seen:
                    seen.add(url)
                    fname = url.split('/')[-1].split('?')[0] or 'zhihu_img.jpg'
                    ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
                    resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources

    def _extract_zhimg_from_html(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://[a-z]\d+\.zhimg\.com/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)[^\s"\'<>]*)', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if 'avatar' in url or url in seen:
                continue
            seen.add(url)
            fname = url.split('/')[-1].split('?')[0] or 'zhihu_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources

    def _dedup(self, resources):
        seen = set()
        result = []
        for r in resources:
            if r['url'] not in seen:
                seen.add(r['url'])
                result.append(r)
        return result


class GithubExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'github.com' in host

    def extract(self, url, html=''):
        resources = []
        parsed = urlparse(url)
        path = parsed.path.strip('/')

        if '/releases' in path or '/archive' in path:
            resources.extend(self._extract_release_assets(html))
        elif '/blob/' in path:
            resources.extend(self._extract_single_file(url))
        elif '/tree/' in path or path.count('/') <= 1:
            resources.extend(self._extract_repo_overview(url, html))
        return resources

    def _extract_release_assets(self, html):
        resources = []
        urls = re.findall(r'href="(/[^/]+/[^/]+/releases/download/[^"]+)"', html)
        for href in urls:
            url = f'https://github.com{href}'
            fname = href.split('/')[-1]
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else ''
            resources.append({'url': url, 'name': fname, 'category': categorize_resource(url), 'extension': ext})
        source_urls = re.findall(r'href="(/[^/]+/[^/]+/archive/refs/[^"]+)"', html)
        for href in source_urls:
            url = f'https://github.com{href}'
            fname = href.split('/')[-1]
            resources.append({'url': url, 'name': fname, 'category': 'archive', 'extension': '.zip'})
        return resources

    def _extract_single_file(self, url):
        raw_url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob', '')
        m = re.search(r'raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/(.+)$', raw_url)
        fname = m.group(1).split('/')[-1] if m else 'file'
        ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else ''
        return [{'url': raw_url, 'name': fname, 'category': categorize_resource(raw_url), 'extension': ext}]

    def _extract_repo_overview(self, url, html):
        resources = []
        raw_urls = re.findall(r'(https://raw\.githubusercontent\.com/[^"\s<>\\]+)', html)
        seen = set()
        for rurl in raw_urls:
            if rurl in seen:
                continue
            seen.add(rurl)
            fname = rurl.split('/')[-1]
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else ''
            resources.append({'url': rurl, 'name': fname, 'category': categorize_resource(rurl), 'extension': ext})
        m = re.match(r'https://github\.com/([^/]+/[^/]+)', url)
        if m:
            repo = m.group(1)
            resources.append({'url': f'https://github.com/{repo}/archive/refs/heads/main.zip', 'name': f'{repo.replace("/", "_")}_main.zip', 'category': 'archive', 'extension': '.zip'})
            resources.append({'url': f'https://github.com/{repo}/archive/refs/heads/master.zip', 'name': f'{repo.replace("/", "_")}_master.zip', 'category': 'archive', 'extension': '.zip'})
        release_urls = re.findall(r'href="(/[^/]+/[^/]+/releases/download/[^"]+)"', html)
        for href in release_urls:
            dl_url = f'https://github.com{href}'
            fname = href.split('/')[-1]
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else ''
            resources.append({'url': dl_url, 'name': fname, 'category': categorize_resource(dl_url), 'extension': ext})
        return resources


class PinterestExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'pinterest.com' in host or 'pin.it' in host

    def extract(self, url, html=''):
        resources = []
        data = self._parse_pws_data(html)
        if data:
            resources.extend(self._extract_from_data(data))
        if not resources:
            resources.extend(self._extract_pinimg_from_html(html))
        if not resources:
            api_data = self._fetch_pin_api(url)
            if api_data:
                resources.extend(self._extract_from_api(api_data))
        return self._dedup(resources)

    def _fetch_pin_api(self, url):
        m = re.search(r'/pin/(\d+)', url)
        if not m:
            return None
        pin_id = m.group(1)
        try:
            api_url = f'https://www.pinterest.com/resource/PinResource/get/'
            params = {'data': json.dumps({'options': {'id': pin_id, 'field_set_key': 'detailed'}})}
            headers = {**BROWSER_HEADERS, 'Referer': 'https://www.pinterest.com/'}
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
            resp = requests.get(api_url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _extract_from_api(self, data):
        resources = []
        d_str = json.dumps(data, ensure_ascii=False)
        orig_urls = re.findall(r'"originals"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(orig_urls):
            url = url.replace('\\/', '/').replace('\\u002F', '/')
            ext = '.' + url.split('?')[0].rsplit('.', 1)[-1] if '.' in url.split('?')[0] else '.jpg'
            resources.append({'url': url, 'name': f'pinterest_orig_{i + 1}{ext}', 'category': 'image', 'extension': ext})
        video_urls = re.findall(r'"video_url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(video_urls):
            url = url.replace('\\/', '/').replace('\\u002F', '/')
            resources.append({'url': url, 'name': f'pinterest_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _parse_pws_data(self, html):
        m = re.search(r'<script[^>]*id=["\']__PWS_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_data(self, data):
        resources = []
        d_str = json.dumps(data, ensure_ascii=False)
        orig_imgs = re.findall(r'"orig"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(orig_imgs):
            url = url.replace('\\/', '/').replace('\\u002F', '/')
            ext = '.' + url.split('/')[-1].split('?')[0].rsplit('.', 1)[-1] if '.' in url.split('?')[0] else '.jpg'
            resources.append({'url': url, 'name': f'pinterest_orig_{i + 1}{ext}', 'category': 'image', 'extension': ext})
        video_urls = re.findall(r'"video_url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(video_urls):
            url = url.replace('\\/', '/').replace('\\u002F', '/')
            resources.append({'url': url, 'name': f'pinterest_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _extract_pinimg_from_html(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://i\.pinimg\.com/originals/[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp))', html)
        if not urls:
            urls = re.findall(r'(https?://i\.pinimg\.com/[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp))', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if url in seen or '/236x/' in url:
                continue
            seen.add(url)
            fname = url.split('/')[-1].split('?')[0] or 'pin_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources

    def _dedup(self, resources):
        seen = set()
        result = []
        for r in resources:
            if r['url'] not in seen:
                seen.add(r['url'])
                result.append(r)
        return result


class PixivExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'pixiv.net' in host or 'pximg.net' in host

    def _build_headers(self):
        headers = {**BROWSER_HEADERS, 'Referer': 'https://www.pixiv.net/'}
        if self.cookies:
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
        return headers

    def extract(self, url, html=''):
        resources = []
        data = self._parse_meta_data(html)
        if data:
            resources.extend(self._extract_from_meta(data))
        if not resources:
            resources.extend(self._extract_pximg_from_html(html))
        og = self._extract_og_image(html)
        for r in og:
            if r['url'] not in [x['url'] for x in resources]:
                resources.append(r)
        return resources

    def _parse_meta_data(self, html):
        m = re.search(r'window\.__NEXT_DATA__\s*=\s*(\{.+?)\s*</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        m = re.search(r'content=["\']application/json["\'][^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_meta(self, data):
        resources = []
        dl_headers = self._build_headers()
        try:
            d_str = json.dumps(data, ensure_ascii=False)
            original_urls = re.findall(r'"original"\s*:\s*"(https?://i\.pximg\.net/[^"]+)"', d_str)
            for i, url in enumerate(original_urls):
                url = url.replace('\\/', '/')
                fname = url.split('/')[-1] or f'pixiv_{i + 1}.png'
                ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.png'
                resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext, 'headers': dl_headers})
        except Exception:
            pass
        return resources

    def _extract_pximg_from_html(self, html):
        resources = []
        seen = set()
        dl_headers = self._build_headers()
        urls = re.findall(r'(https?://i\.pximg\.net/[^\s"\'<>]+)', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if url in seen or '/common/' in url or '/background/' in url:
                continue
            seen.add(url)
            fname = url.split('/')[-1].split('?')[0] or 'pixiv_img.png'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.png'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources

    def _extract_og_image(self, html):
        resources = []
        m = re.search(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        if m:
            url = m.group(1)
            if 'pximg.net' in url or 'pixiv.net' in url:
                resources.append({'url': url, 'name': 'pixiv_og.jpg', 'category': 'image', 'extension': '.jpg', 'headers': self._build_headers()})
        return resources


class CsdnExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'csdn.net' in host or 'csdn.com' in host

    def extract(self, url, html=''):
        resources = []
        resources.extend(self._extract_images(html))
        resources.extend(self._extract_attachments(html))
        return resources

    def _extract_images(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://(?:i-blog|img-blog|gfs)\.csdnimg\.cn/[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp|bmp|svg))[^\s"\'<>]*', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            base_url = url.split('?')[0]
            if base_url in seen:
                continue
            if '/columns/default/' in url or '/dist/pc/' in url:
                continue
            seen.add(base_url)
            fname = base_url.split('/')[-1] or 'csdn_img.jpg'
            if fname.endswith('!1'):
                fname = fname[:-2]
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': base_url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources

    def _extract_attachments(self, html):
        resources = []
        urls = re.findall(r'href="(https?://download\.csdn\.net/[^\s"\'<>]+)"', html)
        for url in urls[:20]:
            fname = url.rstrip('/').split('/')[-1] or 'csdn_download'
            resources.append({'url': url, 'name': fname, 'category': 'document', 'extension': ''})
        return resources


class TiebaExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def _build_headers(self):
        headers = {**BROWSER_HEADERS, 'Referer': 'https://tieba.baidu.com/'}
        if self.cookies:
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
        return headers

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'tieba.baidu.com' in host

    def extract(self, url, html=''):
        resources = []
        if html:
            resources.extend(self._extract_images(html))
            resources.extend(self._extract_videos(html))
        if not resources:
            api_data = self._fetch_tieba_api(url)
            if api_data:
                resources.extend(self._extract_from_api(api_data))
        return resources

    def _fetch_tieba_api(self, url):
        m = re.search(r'/p/(\d+)', url)
        if not m:
            return None
        thread_id = m.group(1)
        try:
            api_url = f'https://tieba.baidu.com/mo/q/m?kz={thread_id}'
            headers = self._build_headers()
            resp = requests.get(api_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _extract_from_api(self, data):
        resources = []
        dl_headers = self._build_headers()
        d_str = json.dumps(data, ensure_ascii=False)
        img_urls = re.findall(r'(https?://imgsa\.baidu\.com/[^\s"\'<>]+\.(?:jpg|png|gif|webp))', d_str)
        img_urls += re.findall(r'(https?://[a-z]\.bdimg\.com/[^\s"\'<>]+\.(?:jpg|png|gif|webp))', d_str)
        seen = set()
        for url in img_urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if url in seen or 'static' in url or 'favicon' in url:
                continue
            seen.add(url)
            fname = url.split('/')[-1] or 'tieba_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources

    def _extract_images(self, html):
        resources = []
        seen = set()
        dl_headers = self._build_headers()
        urls = re.findall(r'(https?://imgsa\.baidu\.com/[^\s"\'<>]+)', html)
        urls += re.findall(r'(https?://[a-z]\.bdimg\.com/[^\s"\'<>]+\.(?:jpg|png|gif)[^\s"\'<>]*)', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\').split('?')[0]
            if url in seen or 'static' in url or 'favicon' in url:
                continue
            seen.add(url)
            fname = url.split('/')[-1] or 'tieba_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext, 'headers': dl_headers})
        return resources

    def _extract_videos(self, html):
        resources = []
        dl_headers = self._build_headers()
        urls = re.findall(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if 'tieba' in url or 'baidu' in url:
                resources.append({'url': url, 'name': 'tieba_video.mp4', 'category': 'video', 'extension': '.mp4', 'headers': dl_headers})
        return resources


class TwitterExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'twitter.com' in host or 'x.com' in host or 't.co' in host

    def extract(self, url, html=''):
        resources = []
        resources.extend(self._extract_og_media(html))
        resources.extend(self._extract_twimg(html))
        data = self._parse_graphql_data(html)
        if data:
            resources.extend(self._extract_from_data(data))
        if not resources and self.cookies:
            api_data = self._fetch_tweet_api(url)
            if api_data:
                resources.extend(self._extract_from_api(api_data))
        resources = [r for r in resources if 'abs.twimg.com' not in r['url']]
        return self._dedup(resources)

    def _fetch_tweet_api(self, url):
        m = re.search(r'/status/(\d+)', url)
        if not m:
            return None
        tweet_id = m.group(1)
        try:
            api_url = f'https://syndication.twitter.com/srv/timeline-profile/api/v1/status/{tweet_id}'
            headers = {**BROWSER_HEADERS, 'Referer': 'https://platform.twitter.com/'}
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
            resp = requests.get(api_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _extract_from_api(self, data):
        resources = []
        d_str = json.dumps(data, ensure_ascii=False)
        img_urls = re.findall(r'(https?://pbs\.twimg\.com/media/[^\s"\\]+\.(?:jpg|png|gif|webp))', d_str)
        for i, url in enumerate(img_urls):
            url = url.replace('\\/', '/').replace('\\u002F', '/')
            if '_orig' not in url:
                orig_url = re.sub(r'\.(jpg|png|gif|webp)$', r'_orig.\1', url)
            else:
                orig_url = url
            fname = orig_url.split('/')[-1].split('?')[0] or f'twitter_img_{i+1}.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': orig_url, 'name': fname, 'category': 'image', 'extension': ext})
        video_urls = re.findall(r'(https?://video\.twimg\.com/[^\s"\\]+\.mp4)', d_str)
        for i, url in enumerate(video_urls):
            url = url.replace('\\/', '/').replace('\\u002F', '/')
            resources.append({'url': url, 'name': f'twitter_video_{i+1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _extract_og_media(self, html):
        resources = []
        og_images = re.findall(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        for i, url in enumerate(og_images):
            if 'twimg' in url:
                orig_url = re.sub(r'/[\w]+\.jpg$', '/orig.jpg', url)
                resources.append({'url': orig_url, 'name': f'twitter_image_{i + 1}_orig.jpg', 'category': 'image', 'extension': '.jpg'})
        og_videos = re.findall(r'property=["\']og:video["\'].*?content=["\'](.*?)["\']', html)
        for i, url in enumerate(og_videos):
            if 'abs.twimg.com' in url:
                continue
            resources.append({'url': url, 'name': f'twitter_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _extract_twimg(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://pbs\.twimg\.com/media/[^\s"\'<>]+\.(?:jpg|png|gif|webp))', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if url in seen:
                continue
            seen.add(url)
            orig_url = re.sub(r'\.(jpg|png|gif|webp)$', r'_orig.\1', url) if '_orig' not in url else url
            fname = orig_url.split('/')[-1].split('?')[0] or 'twitter_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': orig_url, 'name': fname, 'category': 'image', 'extension': ext})
        video_urls = re.findall(r'(https?://video\.twimg\.com/[^\s"\'<>]+\.mp4)', html)
        for i, url in enumerate(video_urls):
            url = url.rstrip('"\'),;]').rstrip('\\')
            if url not in seen:
                seen.add(url)
                resources.append({'url': url, 'name': f'twitter_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _parse_graphql_data(self, html):
        m = re.search(r'__NEXT_DATA__\s*=\s*(\{.+?)\s*</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_data(self, data):
        return []

    def _dedup(self, resources):
        seen = set()
        return [r for r in resources if r['url'] not in seen and not seen.add(r['url'])]


class InstagramExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'instagram.com' in host or 'instagr.am' in host

    def extract(self, url, html=''):
        resources = []
        data = self._parse_shared_data(html)
        if data:
            resources.extend(self._extract_from_data(data))
        resources.extend(self._extract_og_media(html))
        resources.extend(self._extract_cdn_images(html))
        if not resources and self.cookies:
            api_data = self._fetch_instagram_api(url)
            if api_data:
                resources.extend(self._extract_from_api_result(api_data))
        return self._dedup(resources)

    def _fetch_instagram_api(self, url):
        m = re.search(r'/p/([A-Za-z0-9_-]+)', url)
        if not m:
            m = re.search(r'/reel/([A-Za-z0-9_-]+)', url)
        if not m:
            return None
        shortcode = m.group(1)
        try:
            api_url = f'https://www.instagram.com/api/v1/media/{shortcode}/info/'
            headers = {**BROWSER_HEADERS, 'Referer': 'https://www.instagram.com/'}
            cookie_str = '; '.join(f'{k}={v}' for k, v in self.cookies.items() if v)
            if cookie_str:
                headers['Cookie'] = cookie_str
            headers['X-IG-App-ID'] = '936619743392459'
            resp = requests.get(api_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _extract_from_api_result(self, data):
        resources = []
        d_str = json.dumps(data, ensure_ascii=False)
        display_urls = re.findall(r'"display_url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(display_urls[:10]):
            url = url.replace('\\u002F', '/').replace('\\/', '/')
            resources.append({'url': url, 'name': f'instagram_{i + 1}.jpg', 'category': 'image', 'extension': '.jpg'})
        video_urls = re.findall(r'"video_url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(video_urls[:5]):
            url = url.replace('\\u002F', '/').replace('\\/', '/')
            resources.append({'url': url, 'name': f'instagram_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _parse_shared_data(self, html):
        m = re.search(r'window\._sharedData\s*=\s*(\{.+?)\s*;</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        m = re.search(r'window\.__additionalDataLoaded\s*\([^,]+,\s*(\{.+?\})\s*\);', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _extract_from_data(self, data):
        resources = []
        d_str = json.dumps(data, ensure_ascii=False)
        display_urls = re.findall(r'"display_url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(display_urls[:10]):
            url = url.replace('\\u002F', '/').replace('\\/', '/')
            resources.append({'url': url, 'name': f'instagram_{i + 1}.jpg', 'category': 'image', 'extension': '.jpg'})
        video_urls = re.findall(r'"video_url"\s*:\s*"([^"]+)"', d_str)
        for i, url in enumerate(video_urls[:5]):
            url = url.replace('\\u002F', '/').replace('\\/', '/')
            resources.append({'url': url, 'name': f'instagram_video_{i + 1}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _extract_og_media(self, html):
        resources = []
        m = re.search(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        if m:
            url = m.group(1)
            if 'instagram' in url or 'cdninstagram' in url or 'fbcdn' in url:
                resources.append({'url': url, 'name': 'instagram_og.jpg', 'category': 'image', 'extension': '.jpg'})
        m = re.search(r'property=["\']og:video["\'].*?content=["\'](.*?)["\']', html)
        if m:
            resources.append({'url': m.group(1), 'name': 'instagram_video_og.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _extract_cdn_images(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://[^\s"\'<>]*(?:cdninstagram|fbcdn)[^\s"\'<>]*\.(?:jpg|png|mp4)[^\s"\'<>]*)', html)
        for url in urls:
            url = url.replace('\\u002F', '/').replace('\\/', '/').rstrip('"\'),;]').rstrip('\\')
            if url in seen:
                continue
            seen.add(url)
            ext = '.mp4' if '.mp4' in url else '.jpg'
            cat = 'video' if '.mp4' in url else 'image'
            resources.append({'url': url, 'name': f'instagram_cdn_{len(seen)}{ext}', 'category': cat, 'extension': ext})
        return resources

    def _dedup(self, resources):
        seen = set()
        return [r for r in resources if r['url'] not in seen and not seen.add(r['url'])]


class CoolapkExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'coolapk.com' in host

    def extract(self, url, html=''):
        resources = []
        resources.extend(self._extract_images(html))
        return resources

    def _extract_images(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://[^\s"\'<>]*coolapk[^\s"\'<>]*\.(?:jpg|jpeg|png|gif|webp)[^\s"\'<>]*)', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\').split('?')[0]
            if url in seen or 'avatar' in url or 'icon' in url or 'logo' in url:
                continue
            orig_url = re.sub(r'\.xs\.', '.', url)
            orig_url = re.sub(r'\.s\.', '.', orig_url)
            seen.add(orig_url)
            url = orig_url
            fname = url.split('/')[-1] or 'coolapk_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources


class LofterExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'lofter.com' in host

    def extract(self, url, html=''):
        resources = []
        if html:
            resources.extend(self._extract_lofter_images(html))
            og = self._extract_og_media(html)
            for r in og:
                if r['url'] not in [x['url'] for x in resources]:
                    resources.append(r)
        return resources

    def _extract_lofter_images(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://[^\s"\'<>]*(?:lf3-cdn-tos|lofter)[^\s"\'<>]*\.(?:jpg|jpeg|png|gif|webp)[^\s"\'<>]*)', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\').split('?')[0]
            if url in seen:
                continue
            seen.add(url)
            fname = url.split('/')[-1] or 'lofter_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources

    def _extract_og_media(self, html):
        resources = []
        m = re.search(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        if m:
            url = m.group(1).replace('\\/', '/')
            if 'lofter' in url or 'lf3-cdn' in url or '126.net' in url:
                resources.append({'url': url, 'name': 'lofter_og.jpg', 'category': 'image', 'extension': '.jpg'})
        return resources


class NetEaseMusicExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'music.163.com' in host or ('163.com' in host and 'music' in url)

    def extract(self, url, html=''):
        resources = []
        song_id = self._parse_url(url)
        if not song_id:
            return resources
        m = re.search(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        cover_url = m.group(1) if m else None
        api_data = self._fetch_song_api(song_id)
        if api_data:
            resources.extend(self._extract_from_api(api_data, song_id))
        if cover_url and cover_url.replace('http://', 'https://') not in [r['url'].replace('http://', 'https://') for r in resources]:
            cover_url = cover_url.replace('http://', 'https://')
            resources.append({'url': cover_url, 'name': f'netease_cover_{song_id}.jpg', 'category': 'image', 'extension': '.jpg'})
        elif not api_data:
            resources.append({'url': f'https://p1.music.126.net/cover/{song_id}.jpg', 'name': f'netease_cover_{song_id}.jpg', 'category': 'image', 'extension': '.jpg'})
        m = re.search(r'property=["\']og:video["\'].*?content=["\'](.*?)["\']', html)
        if m:
            resources.append({'url': m.group(1), 'name': f'netease_mv_{song_id}.mp4', 'category': 'video', 'extension': '.mp4'})
        return resources

    def _parse_url(self, url):
        m = re.search(r'[?&]id=(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/song/?(\d+)', urlparse(url).path)
        if m:
            return m.group(1)
        return None

    def _fetch_song_api(self, song_id):
        try:
            api_url = 'https://music.163.com/api/song/detail'
            resp = requests.get(api_url, params={'id': song_id, 'ids': f'[{song_id}]'}, headers={**BROWSER_HEADERS, 'Referer': 'https://music.163.com/'}, timeout=15)
            data = resp.json()
            if data.get('code') == 200 and data.get('songs'):
                return data['songs'][0]
        except Exception:
            pass
        return None

    def _extract_from_api(self, song_data, song_id):
        resources = []
        album = song_data.get('album', {})
        cover_url = album.get('picUrl', '') or album.get('blurPicUrl', '')
        if cover_url:
            cover_url = cover_url.replace('http://', 'https://')
            params_idx = cover_url.find('?')
            if params_idx > 0:
                cover_url = cover_url[:params_idx]
            resources.append({'url': cover_url, 'name': f'netease_cover_{song_id}.jpg', 'category': 'image', 'extension': '.jpg'})
        artists = song_data.get('artists', [])
        for artist in artists:
            artist_img = artist.get('img1v1Url', '') or artist.get('picUrl', '')
            if artist_img:
                artist_img = artist_img.replace('http://', 'https://')
                artist_name = artist.get('name', 'unknown')
                if artist_img not in [r['url'] for r in resources]:
                    resources.append({'url': artist_img, 'name': f'netease_artist_{artist_name}.jpg', 'category': 'image', 'extension': '.jpg'})
        mp3_url = song_data.get('mp3Url', '')
        if mp3_url:
            mp3_url = mp3_url.replace('http://', 'https://')
            name = song_data.get('name', f'netease_song_{song_id}')
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
            resources.append({'url': mp3_url, 'name': f'{safe_name}.mp3', 'category': 'audio', 'extension': '.mp3'})
        return resources


class KugouExtractor:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}

    def match(self, url):
        host = (urlparse(url).hostname or '').lower()
        return 'kugou.com' in host

    def extract(self, url, html=''):
        resources = []
        m = re.search(r'property=["\']og:image["\'].*?content=["\'](.*?)["\']', html)
        if m:
            resources.append({'url': m.group(1), 'name': 'kugou_cover.jpg', 'category': 'image', 'extension': '.jpg'})
        m = re.search(r'property=["\']og:video["\'].*?content=["\'](.*?)["\']', html)
        if m:
            resources.append({'url': m.group(1), 'name': 'kugou_mv.mp4', 'category': 'video', 'extension': '.mp4'})
        resources.extend(self._extract_kugou_images(html))
        return resources

    def _extract_kugou_images(self, html):
        resources = []
        seen = set()
        urls = re.findall(r'(https?://[^\s"\'<>]*(?:imgessl|staticssl)\.kugou\.com/[^\s"\'<>]*\.(?:jpg|jpeg|png|webp))[^\s"\'<>]*', html)
        for url in urls:
            url = url.rstrip('"\'),;]').rstrip('\\')
            if url in seen:
                continue
            if 'logo' in url.lower() or 'icon' in url.lower() or 'rank_i' in url:
                continue
            seen.add(url)
            fname = url.split('/')[-1] or 'kugou_img.jpg'
            ext = '.' + fname.rsplit('.', 1)[-1] if '.' in fname else '.jpg'
            resources.append({'url': url, 'name': fname, 'category': 'image', 'extension': ext})
        return resources


def extract_og_media(html):
    from bs4 import BeautifulSoup
    resources = []
    soup = BeautifulSoup(html, 'lxml')
    for prop in ['og:video', 'og:video:url', 'og:video:secure_url']:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            url = tag['content']
            if not any(url.endswith(ext) for ext in ['.mp4', '.webm', '.flv', '.mov', '.avi', '.mkv']):
                if '/video/' not in url and '/play/' not in url:
                    continue
            resources.append({'url': url, 'name': extract_filename(url) or 'video.mp4', 'category': 'video', 'extension': get_extension(url) or '.mp4'})
            break
    for prop in ['og:audio', 'og:audio:url', 'og:audio:secure_url']:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            url = tag['content']
            if not any(url.endswith(ext) for ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma']):
                continue
            resources.append({'url': url, 'name': extract_filename(url) or 'audio.mp3', 'category': 'audio', 'extension': get_extension(url) or '.mp3'})
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
                resources.append({'url': content_url, 'name': extract_filename(content_url) or 'media', 'category': categorize_resource(content_url), 'extension': get_extension(content_url)})
            for embed in item.get('embedUrl', []):
                if embed:
                    resources.append({'url': embed, 'name': extract_filename(embed) or 'embedded_media', 'category': categorize_resource(embed), 'extension': get_extension(embed)})
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
            if 'bilivideo.com' in url or url in seen or len(url) < 15:
                continue
            seen.add(url)
            resources.append({'url': url, 'name': extract_filename(url), 'category': categorize_resource(url), 'extension': get_extension(url)})
    return resources


def _build_all_extractors(cookies):
    all_cookies = cookies or {}
    site_prefixes = ['weibo_', 'zhihu_', 'douyin_', 'pixiv_', 'twitter_', 'instagram_', 'pinterest_', 'tieba_']
    bilibili_cookies = {k: v for k, v in all_cookies.items() if not any(k.startswith(p) for p in site_prefixes)}
    weibo_cookies = {}
    zhihu_cookies = {}
    douyin_cookies = {}
    pixiv_cookies = {}
    twitter_cookies = {}
    instagram_cookies = {}
    pinterest_cookies = {}
    tieba_cookies = {}
    for k, v in all_cookies.items():
        if k.startswith('weibo_'):
            weibo_cookies[k[6:]] = v
        elif k.startswith('zhihu_'):
            zhihu_cookies[k[6:]] = v
        elif k.startswith('douyin_'):
            douyin_cookies[k[7:]] = v
        elif k.startswith('pixiv_'):
            pixiv_cookies[k[6:]] = v
        elif k.startswith('twitter_'):
            twitter_cookies[k[8:]] = v
        elif k.startswith('instagram_'):
            instagram_cookies[k[10:]] = v
        elif k.startswith('pinterest_'):
            pinterest_cookies[k[10:]] = v
        elif k.startswith('tieba_'):
            tieba_cookies[k[6:]] = v
    if 'SUB' in all_cookies:
        weibo_cookies['SUB'] = all_cookies['SUB']
    if 'BDUSS' in all_cookies:
        tieba_cookies['BDUSS'] = all_cookies['BDUSS']
    return [
        BilibiliExtractor(cookies=bilibili_cookies),
        XhsExtractor(cookies=bilibili_cookies),
        WeiboExtractor(cookies=weibo_cookies),
        DouyinExtractor(cookies=douyin_cookies),
        KuaishouExtractor(cookies={}),
        ZhihuExtractor(cookies=zhihu_cookies),
        GithubExtractor(cookies={}),
        PinterestExtractor(cookies=pinterest_cookies),
        PixivExtractor(cookies=pixiv_cookies),
        CsdnExtractor(cookies={}),
        TiebaExtractor(cookies=tieba_cookies),
        TwitterExtractor(cookies=twitter_cookies),
        InstagramExtractor(cookies=instagram_cookies),
        CoolapkExtractor(cookies={}),
        LofterExtractor(cookies=all_cookies if 'LOFTER' in all_cookies else {}),
        NetEaseMusicExtractor(cookies={}),
        KugouExtractor(cookies={}),
    ]


def run_extractors(url, html='', cookies=None):
    all_resources = []
    seen_urls = set()
    cookie_dict = cookies or {}
    extractors = _build_all_extractors(cookie_dict)
    global_filters = [
        'abs.twimg.com/sticky/',
        'abs.twimg.com/videos/',
        'abs.twimg.com/images/',
        'static.cdninstagram.com/rsrc.php',
        's.pximg.net/www/images/',
    ]
    for extractor in extractors:
        if extractor.match(url):
            try:
                extracted = extractor.extract(url, html)
                for r in extracted:
                    if r['url'] not in seen_urls:
                        if any(f in r['url'] for f in global_filters):
                            continue
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
                        if any(f in r['url'] for f in global_filters):
                            continue
                        seen_urls.add(r['url'])
                        all_resources.append(r)
            except Exception:
                pass
    return all_resources
