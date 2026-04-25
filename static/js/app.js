let allResources = [];
let currentCategory = 'all';
let currentTaskId = null;
let eventSource = null;

const CATEGORY_LABELS = {
    document: '文档',
    video: '视频',
    audio: '音频',
    image: '图片',
    archive: '压缩包',
    other: '其他',
};

function toggleCookieSection() {
    const inputs = document.getElementById('cookieInputs');
    const icon = document.getElementById('cookieToggleIcon');
    if (inputs.style.display === 'none') {
        inputs.style.display = 'block';
        icon.textContent = '▲';
    } else {
        inputs.style.display = 'none';
        icon.textContent = '▼';
    }
}

function getCookies() {
    const cookies = {};
    const sessdata = document.getElementById('sessdataInput').value.trim();
    if (sessdata) cookies.SESSDATA = sessdata;
    const xhsCookie = document.getElementById('xhsCookieInput').value.trim();
    if (xhsCookie) {
        if (xhsCookie.includes('=')) {
            xhsCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies[key] = val;
                }
            });
        } else {
            cookies.a1 = xhsCookie;
        }
    }
    const weiboCookie = document.getElementById('weiboCookieInput').value.trim();
    if (weiboCookie) {
        if (weiboCookie.includes('=')) {
            weiboCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['weibo_' + key] = val;
                }
            });
        } else {
            cookies.weibo_SUB = weiboCookie;
        }
    }
    const zhihuCookie = document.getElementById('zhihuCookieInput').value.trim();
    if (zhihuCookie) {
        if (zhihuCookie.includes('=')) {
            zhihuCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['zhihu_' + key] = val;
                }
            });
        } else {
            cookies.zhihu_cookie = zhihuCookie;
        }
    }
    const douyinCookie = document.getElementById('douyinCookieInput').value.trim();
    if (douyinCookie) {
        if (douyinCookie.includes('=')) {
            douyinCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['douyin_' + key] = val;
                }
            });
        } else {
            cookies.douyin_cookie = douyinCookie;
        }
    }
    const pixivCookie = document.getElementById('pixivCookieInput').value.trim();
    if (pixivCookie) {
        if (pixivCookie.includes('=')) {
            pixivCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['pixiv_' + key] = val;
                }
            });
        } else {
            cookies.pixiv_PHPSESSID = pixivCookie;
        }
    }
    const twitterCookie = document.getElementById('twitterCookieInput').value.trim();
    if (twitterCookie) {
        if (twitterCookie.includes('=')) {
            twitterCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['twitter_' + key] = val;
                }
            });
        } else {
            cookies.twitter_auth_token = twitterCookie;
        }
    }
    const instagramCookie = document.getElementById('instagramCookieInput').value.trim();
    if (instagramCookie) {
        if (instagramCookie.includes('=')) {
            instagramCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['instagram_' + key] = val;
                }
            });
        } else {
            cookies.instagram_sessionid = instagramCookie;
        }
    }
    const pinterestCookie = document.getElementById('pinterestCookieInput').value.trim();
    if (pinterestCookie) {
        if (pinterestCookie.includes('=')) {
            pinterestCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['pinterest_' + key] = val;
                }
            });
        } else {
            cookies.pinterest_cookie = pinterestCookie;
        }
    }
    const tiebaCookie = document.getElementById('tiebaCookieInput').value.trim();
    if (tiebaCookie) {
        if (tiebaCookie.includes('=')) {
            tiebaCookie.split(';').forEach(part => {
                const eq = part.indexOf('=');
                if (eq > 0) {
                    const key = part.substring(0, eq).trim();
                    const val = part.substring(eq + 1).trim();
                    if (key && val) cookies['tieba_' + key] = val;
                }
            });
        } else {
            cookies.tieba_BDUSS = tiebaCookie;
        }
    }
    return cookies;
}

function analyzeUrl() {
    const urlInput = document.getElementById('urlInput');
    const url = urlInput.value.trim();
    if (!url) {
        showToast('请输入网址', 'error');
        return;
    }

    const btn = document.getElementById('analyzeBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoading = btn.querySelector('.btn-loading');
    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline';

    fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, cookies: getCookies() }),
    })
    .then(resp => resp.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        allResources = data.resources || [];
        const resultSection = document.getElementById('resultSection');
        resultSection.style.display = 'block';

        document.getElementById('pageTitle').textContent = data.page_title || '未命名页面';
        document.getElementById('pageUrl').textContent = data.final_url || url;

        updateCategoryCounts();
        renderResources();
        showToast(`发现 ${allResources.length} 个资源`, 'success');
    })
    .catch(err => {
        showToast('请求失败: ' + err.message, 'error');
    })
    .finally(() => {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    });
}

function updateCategoryCounts() {
    const counts = { all: 0, document: 0, video: 0, audio: 0, image: 0, archive: 0, other: 0 };
    allResources.forEach(r => {
        counts.all++;
        counts[r.category] = (counts[r.category] || 0) + 1;
    });

    document.getElementById('countAll').textContent = counts.all;
    document.getElementById('countDocument').textContent = counts.document;
    document.getElementById('countVideo').textContent = counts.video;
    document.getElementById('countAudio').textContent = counts.audio;
    document.getElementById('countImage').textContent = counts.image;
    document.getElementById('countArchive').textContent = counts.archive;
    document.getElementById('countOther').textContent = counts.other;
}

function filterByCategory(category, btn) {
    currentCategory = category;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderResources();
}

function renderResources() {
    const tbody = document.getElementById('resourceTableBody');
    const emptyState = document.getElementById('emptyState');
    const resourceList = document.querySelector('.resource-list');

    const filtered = currentCategory === 'all'
        ? allResources
        : allResources.filter(r => r.category === currentCategory);

    if (filtered.length === 0) {
        resourceList.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }

    resourceList.style.display = 'block';
    emptyState.style.display = 'none';

    tbody.innerHTML = filtered.map((r, idx) => {
        const hasHeaders = r.headers ? '<span class="special-badge" title="需要特殊请求头下载">🔐</span>' : '';
        const dashNote = r.name.includes('视频流') ? '<span class="dash-note" title="DASH视频流仅含画面无声音，需配合音频流使用ffmpeg合并">⚠</span>' : '';
        return `
        <tr>
            <td><input type="checkbox" class="resource-checkbox" data-index="${allResources.indexOf(r)}" onchange="updateSelectedCount()"></td>
            <td class="resource-name">${hasHeaders}${dashNote}${escapeHtml(r.name)}</td>
            <td><span class="category-badge ${r.category}">${CATEGORY_LABELS[r.category] || r.category}</span></td>
            <td><span class="extension-tag">${escapeHtml(r.extension || '—')}</span></td>
            <td><a class="resource-url" href="${escapeHtml(r.url)}" target="_blank" title="${escapeHtml(r.url)}">${escapeHtml(truncateUrl(r.url, 45))}</a></td>
        </tr>
        `;
    }).join('');

    updateSelectedCount();
}

function toggleSelectAll() {
    const checked = document.getElementById('selectAll').checked;
    document.querySelectorAll('.resource-checkbox').forEach(cb => {
        cb.checked = checked;
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('.resource-checkbox:checked');
    const count = checkboxes.length;
    document.getElementById('selectedCount').textContent = `已选 ${count} 项`;
    document.getElementById('downloadBtn').disabled = count === 0;

    const allCheckboxes = document.querySelectorAll('.resource-checkbox');
    document.getElementById('selectAll').checked = allCheckboxes.length > 0 && count === allCheckboxes.length;
}

function getSelectedResources() {
    const selected = [];
    document.querySelectorAll('.resource-checkbox:checked').forEach(cb => {
        const idx = parseInt(cb.dataset.index);
        if (allResources[idx]) {
            const res = {
                url: allResources[idx].url,
                name: allResources[idx].name,
            };
            if (allResources[idx].headers) {
                res.headers = allResources[idx].headers;
            }
            selected.push(res);
        }
    });
    return selected;
}

function startDownload() {
    const selected = getSelectedResources();
    if (selected.length === 0) {
        showToast('请至少选择一个资源', 'error');
        return;
    }

    document.getElementById('downloadBtn').disabled = true;

    fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resources: selected, save_dir: '' }),
    })
    .then(resp => resp.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'error');
            document.getElementById('downloadBtn').disabled = false;
            return;
        }
        currentTaskId = data.task_id;
        showProgressSection(selected.length);
        listenProgress(data.task_id);
    })
    .catch(err => {
        showToast('下载请求失败: ' + err.message, 'error');
        document.getElementById('downloadBtn').disabled = false;
    });
}

function showProgressSection(total) {
    const section = document.getElementById('progressSection');
    section.style.display = 'block';
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('progressText').textContent = `0 / ${total}`;
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('successCount').textContent = '0';
    document.getElementById('failedCount').textContent = '0';
    document.getElementById('currentFile').textContent = '';
    document.getElementById('cancelDownloadBtn').style.display = 'inline-block';
    section.scrollIntoView({ behavior: 'smooth' });
}

function listenProgress(taskId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/api/download/progress?task_id=${taskId}`);

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);

        if (data.status === 'done') {
            eventSource.close();
            eventSource = null;
            currentTaskId = null;

            const total = data.total || 0;
            const completed = data.completed_count || 0;
            const failed = data.failed_count || 0;
            const pct = total > 0 ? Math.round(((completed + failed) / total) * 100) : 100;

            document.getElementById('progressBar').style.width = pct + '%';
            document.getElementById('progressText').textContent = `${completed + failed} / ${total}`;
            document.getElementById('progressPercent').textContent = pct + '%';
            document.getElementById('successCount').textContent = completed;
            document.getElementById('failedCount').textContent = failed;
            document.getElementById('currentFile').textContent = data.message || '下载完成';
            document.getElementById('cancelDownloadBtn').style.display = 'none';
            document.getElementById('downloadBtn').disabled = false;

            showToast(data.message || '下载完成', failed > 0 ? 'info' : 'success');
            return;
        }

        const total = data.total || 1;
        const current = data.current || 0;
        const pct = Math.round((current / total) * 100);

        document.getElementById('progressBar').style.width = pct + '%';
        document.getElementById('progressText').textContent = `${current} / ${total}`;
        document.getElementById('progressPercent').textContent = pct + '%';
        document.getElementById('successCount').textContent = data.completed_count || 0;
        document.getElementById('failedCount').textContent = data.failed_count || 0;

        if (data.filename) {
            document.getElementById('currentFile').textContent = '正在下载: ' + data.filename;
        }
    };

    eventSource.onerror = function() {
        eventSource.close();
        eventSource = null;
    };
}

function cancelDownload() {
    if (!currentTaskId) return;

    fetch('/api/download/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: currentTaskId }),
    })
    .then(() => {
        showToast('正在取消下载...', 'info');
        document.getElementById('cancelDownloadBtn').disabled = true;
    });
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncateUrl(url, maxLen) {
    if (!url || url.length <= maxLen) return url || '';
    return url.substring(0, maxLen) + '...';
}

function showToast(message, type) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type || 'info'}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 3000);
}

document.getElementById('urlInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        analyzeUrl();
    }
});
