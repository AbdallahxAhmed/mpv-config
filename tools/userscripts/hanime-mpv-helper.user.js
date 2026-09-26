// ==UserScript==
// @name         Hanime.tv MPV & Turbo Downloader Stream Grabber
// @namespace    https://github.com/AbdallahxAhmed/mpv-config
// @version      2.1
// @description  Intercepts Hanime video streams, auto-syncs to MPV/yt-dlp, and provides a floating 1-click play & download bar
// @author       mpv-config
// @match        https://hanime.tv/*
// @grant        GM_setClipboard
// @grant        GM_notification
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    const DAEMON_URL = 'http://127.0.0.1:8765';
    let capturedStreamUrl = null;
    let streamSlug = '';

    function getSlug() {
        const parts = window.location.pathname.split('/').filter(Boolean);
        return parts.length > 0 ? parts[parts.length - 1] : '';
    }

    function isVideoPage() {
        const path = window.location.pathname;
        return path.includes('/videos/hentai/') || path.includes('/hentai/video/');
    }

    // ─── Stream Interception ──────────────────────────────────────────────

    function onStreamFound(url) {
        if (!url || typeof url !== 'string') return;
        if (!url.includes('.m3u8') && !url.includes('/manifest')) return;
        if (capturedStreamUrl === url) return;

        capturedStreamUrl = url;
        streamSlug = getSlug();
        const pageTitle = document.title || streamSlug;

        console.log('[MPV Grabber] Captured M3U8 stream:', url);

        // 1. Auto-copy stream to clipboard for Watch-Clipboard.cmd / MPV
        try {
            if (typeof GM_setClipboard !== 'undefined') {
                GM_setClipboard(url);
            } else if (navigator.clipboard) {
                navigator.clipboard.writeText(url);
            }
        } catch (_) {}

        // 2. Dispatch to local daemon if running
        const payload = JSON.stringify({
            slug: streamSlug,
            url: url,
            title: pageTitle,
            page_url: window.location.href,
            cookies: document.cookie || ''
        });

        if (typeof GM_xmlhttpRequest !== 'undefined') {
            GM_xmlhttpRequest({
                method: 'POST',
                url: `${DAEMON_URL}/stream`,
                headers: { 'Content-Type': 'application/json' },
                data: payload,
                onerror: () => {}
            });
            if (document.cookie) {
                GM_xmlhttpRequest({
                    method: 'POST',
                    url: `${DAEMON_URL}/sync`,
                    headers: { 'Content-Type': 'application/json' },
                    data: JSON.stringify({ cookies: document.cookie, domain: 'hanime.tv' }),
                    onerror: () => {}
                });
            }
        } else {
            fetch(`${DAEMON_URL}/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                mode: 'cors'
            }).catch(() => {});
        }

        updatePillUI();
    }

    // Hook fetch
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            const url = (args[0] && typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url ? args[0].url : '');
            onStreamFound(url);
        } catch (_) {}
        return originalFetch.apply(this, args);
    };

    // Hook XMLHttpRequest
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        try {
            onStreamFound(url);
        } catch (_) {}
        return originalOpen.apply(this, [method, url, ...rest]);
    };

    // ─── Floating Control Pill ───────────────────────────────────────────

    function updatePillUI() {
        const pill = document.getElementById('mpv-grabber-pill');
        if (!pill) return;

        const statusText = document.getElementById('mpv-status-text');
        const dlBtn = document.getElementById('mpv-dl-btn');
        const playBtn = document.getElementById('mpv-play-btn');

        if (capturedStreamUrl) {
            pill.style.borderColor = '#10b981';
            pill.style.boxShadow = '0 0 25px rgba(16, 185, 129, 0.6)';
            if (statusText) statusText.innerHTML = '⚡ Stream Ready (Copied)';
            if (dlBtn) dlBtn.style.display = 'inline-block';
            if (playBtn) playBtn.style.display = 'inline-block';
        } else {
            pill.style.borderColor = '#7c3aed';
            pill.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.8)';
            if (statusText) statusText.innerHTML = '🎬 Click Play on Video';
        }
    }

    function createPill() {
        if (!isVideoPage()) {
            const existing = document.getElementById('mpv-grabber-pill');
            if (existing) existing.remove();
            return;
        }

        if (document.getElementById('mpv-grabber-pill')) return;

        const targetRoot = document.body || document.documentElement;
        if (!targetRoot) return;

        const pill = document.createElement('div');
        pill.id = 'mpv-grabber-pill';
        pill.style.cssText = `
            position: fixed !important;
            bottom: 24px !important;
            right: 24px !important;
            z-index: 2147483647 !important;
            display: flex !important;
            align-items: center !important;
            gap: 10px !important;
            background: #0f172a !important;
            border: 2px solid #7c3aed !important;
            border-radius: 12px !important;
            padding: 8px 14px !important;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8) !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            color: #ffffff !important;
            user-select: none !important;
            transition: all 0.3s ease !important;
        `;

        // Status indicator
        const statusSpan = document.createElement('span');
        statusSpan.id = 'mpv-status-text';
        statusSpan.style.cssText = `
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #e2e8f0 !important;
        `;
        statusSpan.innerHTML = '🎬 Click Play on Video';

        // Play in MPV Button
        const playBtn = document.createElement('button');
        playBtn.id = 'mpv-play-btn';
        playBtn.innerHTML = '🎬 Play in MPV';
        playBtn.style.cssText = `
            display: none;
            padding: 7px 12px !important;
            background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            cursor: pointer !important;
            transition: transform 0.1s !important;
        `;
        playBtn.onclick = () => {
            const url = capturedStreamUrl || window.location.href;
            fetch(`${DAEMON_URL}/play`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            }).then(() => {
                playBtn.innerHTML = '✓ Playing!';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2000);
            }).catch(() => {
                // If daemon isn't running, URL is already in clipboard!
                alert('Stream URL copied to clipboard! Paste directly into MPV (Ctrl+V) or terminal.');
            });
        };

        // Turbo Download Button
        const dlBtn = document.createElement('button');
        dlBtn.id = 'mpv-dl-btn';
        dlBtn.innerHTML = '⚡ 16x Download';
        dlBtn.style.cssText = `
            display: none;
            padding: 7px 12px !important;
            background: linear-gradient(135deg, #059669, #10b981) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            cursor: pointer !important;
            transition: transform 0.1s !important;
        `;
        dlBtn.onclick = () => {
            const url = capturedStreamUrl || window.location.href;
            fetch(`${DAEMON_URL}/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            }).then(() => {
                dlBtn.innerHTML = '✓ Started!';
                setTimeout(() => { dlBtn.innerHTML = '⚡ 16x Download'; }, 2000);
            }).catch(() => {
                alert('Stream URL copied to clipboard! Run Watch-Clipboard.cmd or "dl <link>" in terminal.');
            });
        };

        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.id = 'mpv-copy-btn';
        copyBtn.innerHTML = '📋 Copy';
        copyBtn.style.cssText = `
            padding: 7px 10px !important;
            background: rgba(255, 255, 255, 0.1) !important;
            color: #cbd5e1 !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            border-radius: 8px !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            cursor: pointer !important;
        `;
        copyBtn.onclick = () => {
            const url = capturedStreamUrl || window.location.href;
            if (typeof GM_setClipboard !== 'undefined') {
                GM_setClipboard(url);
            } else if (navigator.clipboard) {
                navigator.clipboard.writeText(url);
            }
            copyBtn.innerHTML = '✓ Copied';
            setTimeout(() => { copyBtn.innerHTML = '📋 Copy'; }, 2000);
        };

        pill.appendChild(statusSpan);
        pill.appendChild(playBtn);
        pill.appendChild(dlBtn);
        pill.appendChild(copyBtn);
        targetRoot.appendChild(pill);

        updatePillUI();
    }

    // Periodic check to ensure pill survives SPA page transitions & video player inspection
    setInterval(() => {
        createPill();
        // Also check if video element has loaded a direct src
        const v = document.querySelector('video');
        if (v && v.src) {
            onStreamFound(v.src);
        }
    }, 1000);

    // Initial check
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createPill);
    } else {
        createPill();
    }
})();
