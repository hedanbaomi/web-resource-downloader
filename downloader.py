import os
import re
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

import requests

from scraper import BROWSER_HEADERS

_active_tasks = {}
_task_lock = threading.Lock()


def get_filename_from_url(url, response=None):
    filename = None
    if response:
        content_disposition = response.headers.get('Content-Disposition', '')
        if content_disposition:
            matches = re.findall(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';]+)', content_disposition)
            if matches:
                filename = unquote(matches[0].strip())

    if not filename:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = path.split('/')[-1] if '/' in path else path

    if not filename or filename.endswith('/'):
        filename = f'download_{uuid.uuid4().hex[:8]}'

    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return filename


def _unique_filepath(directory, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    filepath = os.path.join(directory, filename)
    while os.path.exists(filepath):
        filepath = os.path.join(directory, f"{base}_{counter}{ext}")
        counter += 1
    return filepath


def download_file(url, save_dir, max_retries=3):
    for attempt in range(max_retries):
        try:
            head_resp = requests.head(url, headers=BROWSER_HEADERS, timeout=15, allow_redirects=True)
            content_type = head_resp.headers.get('Content-Type', '')
            file_size = head_resp.headers.get('Content-Length')

            filename = get_filename_from_url(url, head_resp)
            filepath = _unique_filepath(save_dir, filename)

            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=60, allow_redirects=True, stream=True)
            resp.raise_for_status()

            if not filename or filename == f'download_{uuid.uuid4().hex[:8]}':
                filename = get_filename_from_url(url, resp)
                filepath = _unique_filepath(save_dir, filename)

            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            return {
                'status': 'completed',
                'url': url,
                'filename': filename,
                'filepath': filepath,
                'size': downloaded,
            }
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            return {
                'status': 'error',
                'url': url,
                'filename': filename if 'filename' in dir() else get_filename_from_url(url),
                'error': str(e),
            }


def batch_download(task_id, resources, save_dir, max_workers=4):
    os.makedirs(save_dir, exist_ok=True)
    total = len(resources)

    with _task_lock:
        _active_tasks[task_id] = {
            'total': total,
            'completed': 0,
            'failed': 0,
            'results': [],
            'cancelled': False,
            'current_file': '',
            'status': 'running',
        }

    task_info = _active_tasks[task_id]

    def do_download(resource):
        if task_info['cancelled']:
            return {'status': 'cancelled', 'url': resource['url'], 'filename': resource.get('name', '')}

        task_info['current_file'] = resource.get('name', resource['url'])
        result = download_file(resource['url'], save_dir)
        return result

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, resource in enumerate(resources):
                future = executor.submit(do_download, resource)
                futures[future] = idx

            for future in as_completed(futures):
                if task_info['cancelled']:
                    break
                result = future.result()
                task_info['results'].append(result)

                if result['status'] == 'completed':
                    task_info['completed'] += 1
                elif result['status'] == 'error':
                    task_info['failed'] += 1

                current_count = task_info['completed'] + task_info['failed']
                progress_data = {
                    'current': current_count,
                    'total': total,
                    'filename': result.get('filename', ''),
                    'status': result['status'],
                    'completed_count': task_info['completed'],
                    'failed_count': task_info['failed'],
                    'message': f"下载完成: {result.get('filename', '')}" if result['status'] == 'completed' else f"下载失败: {result.get('error', '未知错误')}",
                }
                task_info.setdefault('progress_queue', []).append(progress_data)

        task_info['status'] = 'cancelled' if task_info['cancelled'] else 'completed'
    except Exception as e:
        task_info['status'] = 'error'
        task_info['error'] = str(e)


def cancel_task(task_id):
    with _task_lock:
        if task_id in _active_tasks:
            _active_tasks[task_id]['cancelled'] = True


def get_task_info(task_id):
    with _task_lock:
        return _active_tasks.get(task_id)


def pop_progress(task_id):
    with _task_lock:
        task_info = _active_tasks.get(task_id)
        if task_info and 'progress_queue' in task_info:
            items = task_info['progress_queue'][:]
            task_info['progress_queue'] = []
            return items
    return []
