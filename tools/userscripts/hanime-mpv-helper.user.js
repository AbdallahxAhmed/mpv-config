// ==UserScript==
// @name         Hanime.tv MPV & Turbo Downloader Stream Grabber
// @namespace    https://github.com/AbdallahxAhmed/mpv-config
// @version      2.0
// @description  Intercepts Hanime video streams, auto-syncs Cloudflare cookies to MPV/yt-dlp, and provides 1-click play & download
// @author       mpv-config
// @match        https://hanime.tv/videos/hentai/*
// @match        https://hanime.tv/hentai/video/*
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
    let lastM3u8Url = null;

    function getSlug() {
        return window.location.pathname.split('/').filter(Boolean).pop() || '';
    }

    // ─── Auto-Sync Cookies to Local Daemon / yt-dlp ───────────────────────
    function autoSyncCookies() {
        if (!document.cookie) return;
        const payload = JSON.stringify({
            cookies: document.cookie,
            domain: 'hanime.tv',
            url: window.location.href
        });

        if (typeof GM_xmlhttpRequest !== 'undefined') {
            GM_xmlhttpRequest({
                method: 'POST',
                url: `${DAEMON_URL}/sync`,
                headers: { 'Content-Type': 'application/json' },
                data: payload,
                onerror: () => {}
            });
        } else {
            fetch(`${DAEMON_URL}/sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                mode: 'cors'
            }).catch(() => {});
        }
    }

    // Run cookie sync on load and after 2 seconds
    window.addEventListener('load', autoSyncCookies);
    setTimeout(autoSyncCookies, 2000);
    setTimeout(autoSyncCookies, 5000);

    // ─── Intercept Stream Manifests ───────────────────────────────────────
    function onStreamDetected(url) {
        if (!url || (!url.includes('.m3u8') && !url.includes('/manifest'))) return;
        lastM3u8Url = url;
        const slug = getSlug();
        const title = document.title || slug;

        // Auto-post stream to local daemon
        const payload = JSON.stringify({
            slug: slug,
            url: url,
            title: title,
            page_url: window.location.href
        });

        if (typeof GM_xmlhttpRequest !== 'undefined') {
            GM_xmlhttpRequest({
                method: 'POST',
                url: `${DAEMON_URL}/stream`,
                headers: { 'Content-Type': 'application/json' },
                data: payload,
                onerror: () => {}
            });
        } else {
            fetch(`${DAEMON_URL}/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                mode: 'cors'
            }).catch(() => {});
        }

        updateUI(url);
    }

    // Hook fetch & XMLHttpRequest
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const url = (args[0] && typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url ? args[0].url : '');
        if (url && (url.includes('.m3u8') || url.includes('/manifest'))) {
            onStreamDetected(url);
        }
        return originalFetch.apply(this, args);
    };

    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        if (typeof url === 'string' && (url.includes('.m3u8') || url.includes('/manifest'))) {
            onStreamDetected(url);
        }
        return originalOpen.apply(this, [method, url, ...rest]);
    };

    // ─── Floating MPV Actions Pill ────────────────────────────────────────
    function createPill() {
        if (document.getElementById('mpv-companion-pill')) return;

        const container = document.createElement('div');
        container.id = 'mpv-companion-pill';
        container.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999999;
            display: flex;
            gap: 10px;
            background: rgba(15, 23, 42, 0.95);
            padding: 8px 12px;
            border-radius: 12px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        `;

        // Button 1: Play in MPV
        const playBtn = document.createElement('button');
        playBtn.id = 'mpv-play-btn';
        playBtn.innerHTML = '🎬 Play in MPV';
        playBtn.style.cssText = `
            padding: 8px 14px;
            background: linear-gradient(135deg, #7c3aed, #4f46e5);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        `;
        playBtn.onclick = () => {
            const targetUrl = lastM3u8Url || window.location.href;
            fetch(`${DAEMON_URL}/play`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: targetUrl })
            }).then(() => {
                playBtn.innerHTML = '✓ Playing in MPV!';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2500);
            }).catch(() => {
                alert('MPV Sync Daemon not running on port 8765. Ensure MPV helper is running or paste URL in MPV.');
            });
        };

        // Button 2: Turbo Download (16x)
        const dlBtn = document.createElement('button');
        dlBtn.id = 'mpv-dl-btn';
        dlBtn.innerHTML = '⚡ Turbo Download';
        dlBtn.style.cssText = `
            padding: 8px 14px;
            background: linear-gradient(135deg, #059669, #10b981);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        `;
        dlBtn.onclick = () => {
            const targetUrl = lastM3u8Url || window.location.href;
            fetch(`${DAEMON_URL}/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: targetUrl })
            }).then(() => {
                dlBtn.innerHTML = '✓ Downloading!';
                setTimeout(() => { dlBtn.innerHTML = '⚡ Turbo Download'; }, 2500);
            }).catch(() => {
                if (lastM3u8Url) {
                    if (typeof GM_setClipboard !== 'undefined') GM_setClipboard(lastM3u8Url);
                    else navigator.clipboard.writeText(lastM3u8Url);
                    alert('Stream link copied to clipboard! Paste into your terminal or MPV.');
                }
            });
        };

        // Button 3: Copy Stream
        const copyBtn = document.createElement('button');
        copyBtn.id = 'mpv-copy-btn';
        copyBtn.innerHTML = '📋 Copy Link';
        copyBtn.style.cssText = `
            padding: 8px 10px;
            background: rgba(255, 255, 255, 0.1);
            color: #e2e8f0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        `;
        copyBtn.onclick = () => {
            const link = lastM3u8Url || window.location.href;
            if (typeof GM_setClipboard !== 'undefined') GM_setClipboard(link);
            else navigator.clipboard.writeText(link);
            copyBtn.innerHTML = '✓ Copied!';
            setTimeout(() => { copyBtn.innerHTML = '📋 Copy Link'; }, 2000);
        };

        container.appendChild(playBtn);
        container.appendChild(dlBtn);
        container.appendChild(copyBtn);
        document.body.appendChild(container);
    }

    function updateUI(url) {
        const pill = document.getElementById('mpv-companion-pill');
        if (pill) {
            pill.style.boxShadow = '0 0 25px rgba(124, 58, 237, 0.8)';
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createPill);
    } else {
        createPill();
    }
})();
