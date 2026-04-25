import json
import os
import time
import uuid
import threading

from flask import Flask, render_template, request, jsonify, Response
from scraper import fetch_page, parse_resources, _normalize_url
from extractors import run_extractors
from downloader import batch_download, pop_progress, get_task_info, cancel_task

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': '请输入网址'}), 400

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    cookies = data.get('cookies', {})
    result = fetch_page(url, cookies=cookies)

    html = result.get('html')
    final_url = result.get('final_url', url)

    if html is None:
        extracted = run_extractors(final_url, '', cookies=cookies)
        if extracted:
            return jsonify({
                'resources': extracted,
                'page_title': '',
                'final_url': final_url,
            })
        error_msg = result.get('error', '无法访问该网页')
        return jsonify({'error': f'网页获取失败: {error_msg}'}), 400

    parsed = parse_resources(result['final_url'], result['html'])

    cookies = data.get('cookies', {})

    extracted = run_extractors(result['final_url'], result['html'], cookies=cookies)

    seen_urls = set(_normalize_url(r['url']) for r in parsed['resources'])
    for r in extracted:
        if _normalize_url(r['url']) not in seen_urls:
            seen_urls.add(_normalize_url(r['url']))
            parsed['resources'].append(r)

    return jsonify({
        'resources': parsed['resources'],
        'page_title': parsed['page_title'],
        'final_url': result['final_url'],
    })


@app.route('/api/download', methods=['POST'])
def download():
    data = request.get_json(silent=True) or {}
    resources = data.get('resources', [])
    save_dir = data.get('save_dir', '').strip()

    if not resources:
        return jsonify({'error': '请至少选择一个资源'}), 400

    if not save_dir:
        save_dir = DOWNLOAD_DIR
    elif not os.path.isabs(save_dir):
        save_dir = os.path.join(DOWNLOAD_DIR, save_dir)

    task_id = uuid.uuid4().hex

    thread = threading.Thread(
        target=batch_download,
        args=(task_id, resources, save_dir),
        daemon=True,
    )
    thread.start()

    return jsonify({'task_id': task_id})


@app.route('/api/download/progress')
def download_progress():
    task_id = request.args.get('task_id', '')

    def generate():
        while True:
            items = pop_progress(task_id)
            for item in items:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

            task_info = get_task_info(task_id)
            if task_info and task_info['status'] in ('completed', 'error'):
                final_data = {
                    'status': 'done',
                    'completed_count': task_info['completed'],
                    'failed_count': task_info['failed'],
                    'total': task_info['total'],
                    'message': '下载完成' if task_info['failed'] == 0 else f"下载完成，{task_info['failed']}个文件失败",
                }
                yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
                break

            if not task_id:
                break

            time.sleep(0.3)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/download/cancel', methods=['POST'])
def download_cancel():
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id', '')
    if task_id:
        cancel_task(task_id)
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
