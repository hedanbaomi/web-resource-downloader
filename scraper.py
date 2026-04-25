import re
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
import requests

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

RESOURCE_EXTENSIONS = {
    'document': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.epub', '.md'},
    'video': {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'},
    'audio': {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'},
    'image': {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico', '.tiff', '.avif'},
    'archive': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'},
}

ALL_RESOURCE_EXTENSIONS = set()
for exts in RESOURCE_EXTENSIONS.values():
    ALL_RESOURCE_EXTENSIONS.update(exts)


def fetch_page(url, cookies=None):
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    session.headers.update({
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    })
    host = (urlparse(url).hostname or '').lower()
    site_cookies = {}
    if cookies and isinstance(cookies, dict):
        site_cookies = cookies
    if host and 'zhihu.com' in host:
        site_cookies.setdefault('_xsrf', 'dummy')
        session.headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in site_cookies.items()) if site_cookies else ''
        session.headers['Referer'] = 'https://www.zhihu.com/'
    elif host and 'weibo.com' in host:
        session.headers['Referer'] = 'https://weibo.com/'
        if site_cookies:
            session.headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in site_cookies.items())
    elif host and 'douyin.com' in host:
        session.headers['Referer'] = 'https://www.douyin.com/'
    elif site_cookies:
        session.headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in site_cookies.items())
    try:
        response = session.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        if response.encoding and response.encoding.lower() != 'utf-8':
            response.encoding = response.apparent_encoding
        return {
            'html': response.text,
            'final_url': response.url,
            'status_code': response.status_code,
        }
    except requests.RequestException as e:
        return {
            'html': None,
            'final_url': url,
            'status_code': None,
            'error': str(e),
        }


def resolve_url(base_url, resource_path):
    if not resource_path:
        return None
    resource_path = resource_path.strip()
    if resource_path.startswith(('data:', 'javascript:', 'mailto:', 'tel:', '#')):
        return None
    try:
        absolute_url = urljoin(base_url, resource_path)
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ('http', 'https'):
            return None
        return absolute_url
    except Exception:
        return None


def categorize_resource(url):
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()
    for dot_pos in range(path.rfind('.'), len(path)):
        pass

    for category, extensions in RESOURCE_EXTENSIONS.items():
        for ext in extensions:
            if path.endswith(ext):
                return category
    return 'other'


def get_extension(url):
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = path.split('/')[-1] if '/' in path else path
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[-1].lower()
        if ext in ALL_RESOURCE_EXTENSIONS:
            return ext
    return ''


def extract_filename(url):
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = path.split('/')[-1] if '/' in path else path
    if not filename or filename.endswith('/'):
        filename = 'unnamed_resource'
    return filename


def _is_resource_url(url):
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()

    for ext in ALL_RESOURCE_EXTENSIONS:
        if path.endswith(ext):
            return True

    known_media_hosts = ['cdn', 'media', 'static', 'assets', 'upload', 'download']
    host_lower = parsed.hostname.lower() if parsed.hostname else ''
    if any(kw in host_lower for kw in known_media_hosts):
        if '.' in path.split('/')[-1]:
            return False
    return False


def _extract_links_from_attributes(soup, base_url, tag_attrs):
    links = set()
    for tag_name, attr_name in tag_attrs:
        for tag in soup.find_all(tag_name):
            value = tag.get(attr_name)
            if value:
                if isinstance(value, list):
                    value = ' '.join(value)
                for part in value.split():
                    url = resolve_url(base_url, part)
                    if url:
                        links.add(url)
    return links


def _extract_css_urls(soup, base_url):
    links = set()
    for style in soup.find_all('style'):
        css_text = style.string or ''
        for match in re.findall(r'url\(["\']?(.*?)["\']?\)', css_text):
            url = resolve_url(base_url, match)
            if url:
                links.add(url)

    for tag in soup.find_all(style=True):
        css_text = tag.get('style', '')
        for match in re.findall(r'url\(["\']?(.*?)["\']?\)', css_text):
            url = resolve_url(base_url, match)
            if url:
                links.add(url)
    return links


def parse_resources(url, html):
    soup = BeautifulSoup(html, 'lxml')
    final_url = url

    base_tag = soup.find('base', href=True)
    if base_tag:
        final_url = base_tag['href']

    tag_attrs = [
        ('a', 'href'),
        ('img', 'src'),
        ('img', 'data-src'),
        ('video', 'src'),
        ('video', 'poster'),
        ('audio', 'src'),
        ('source', 'src'),
        ('link', 'href'),
        ('script', 'src'),
        ('embed', 'src'),
        ('object', 'data'),
        ('iframe', 'src'),
    ]

    all_links = set()
    all_links.update(_extract_links_from_attributes(soup, final_url, tag_attrs))
    all_links.update(_extract_css_urls(soup, final_url))

    resources = []
    seen_urls = set()

    for link in sorted(all_links):
        normalized = _normalize_url(link)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)

        category = categorize_resource(link)
        filename = extract_filename(link)
        extension = get_extension(link)

        resources.append({
            'url': link,
            'name': filename,
            'category': category,
            'extension': extension,
        })

    resources.sort(key=lambda r: (
        {'document': 0, 'video': 1, 'audio': 2, 'image': 3, 'archive': 4, 'other': 5}.get(r['category'], 5),
        r['name'].lower()
    ))

    page_title = ''
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        page_title = title_tag.string.strip()

    return {
        'resources': resources,
        'page_title': page_title,
    }


def _normalize_url(url):
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.hostname or ''}{parsed.path}"
    if parsed.query:
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                          'fbclid', 'gclid', 'ref', 'source'}
        params = []
        for part in parsed.query.split('&'):
            if '=' in part:
                key = part.split('=')[0]
                if key not in tracking_params:
                    params.append(part)
        if params:
            normalized += '?' + '&'.join(params)
    return normalized.lower().rstrip('/')
