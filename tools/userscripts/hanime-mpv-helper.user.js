// ==UserScript==
// @name         Hanime MPV Stream Grabber
// @namespace    https://github.com/AbdallahxAhmed/mpv-config
// @version      3.0
// @description  Captures direct M3U8 video stream from Hanime and copies it to clipboard for 1-click playback in MPV or 16x turbo download
// @author       mpv-config
// @match        https://hanime.tv/*
// @grant        GM_setClipboard
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let capturedStreamUrl = null;

    function isVideoPage() {
        const path = window.location.pathname;
        return path.includes('/videos/hentai/') || path.includes('/hentai/video/');
    }

    function copyStreamToClipboard(url) {
        if (!url) return;
        try {
            if (typeof GM_setClipboard !== 'undefined') {
                GM_setClipboard(url);
            } else if (navigator.clipboard) {
                navigator.clipboard.writeText(url);
            }
        } catch (_) {}
    }

    // ─── Stream Interception (fetch + XHR + video element) ───────────────

    function handleStreamUrl(url) {
        if (!url || typeof url !== 'string') return;
        if (!url.includes('.m3u8') && !url.includes('/manifest')) return;
        if (capturedStreamUrl === url) return;

        capturedStreamUrl = url;
        console.log('[Hanime MPV Grabber] Intercepted M3U8 stream:', url);

        // Auto-copy to clipboard immediately
        copyStreamToClipboard(url);

        updatePill(true);
    }

    // 1. Hook fetch
    const origFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            const url = (args[0] && typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url ? args[0].url : '');
            handleStreamUrl(url);
        } catch (_) {}
        return origFetch.apply(this, args);
    };

    // 2. Hook XMLHttpRequest
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        try {
            handleStreamUrl(url);
        } catch (_) {}
        return origOpen.apply(this, [method, url, ...rest]);
    };

    // ─── Floating Control Pill ───────────────────────────────────────────

    function updatePill(isReady) {
        const pill = document.getElementById('mpv-grabber-pill');
        if (!pill) return;

        const label = document.getElementById('mpv-pill-label');
        const copyBtn = document.getElementById('mpv-pill-copy');

        if (isReady && capturedStreamUrl) {
            pill.style.border = '2px solid #10b981';
            pill.style.boxShadow = '0 0 25px rgba(16, 185, 129, 0.7)';
            if (label) {
                label.innerHTML = '⚡ Stream Copied! (Ready for MPV / dl)';
                label.style.color = '#34d399';
            }
            if (copyBtn) copyBtn.style.display = 'inline-block';
        } else {
            pill.style.border = '2px solid #7c3aed';
            pill.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.8)';
            if (label) {
                label.innerHTML = '🎬 Click Play on Video';
                label.style.color = '#e2e8f0';
            }
            if (copyBtn) copyBtn.style.display = 'none';
        }
    }

    function createPill() {
        if (!isVideoPage()) {
            const existing = document.getElementById('mpv-grabber-pill');
            if (existing) existing.remove();
            capturedStreamUrl = null;
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
            padding: 9px 15px !important;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8) !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            color: #ffffff !important;
            user-select: none !important;
            transition: all 0.3s ease !important;
        `;

        const label = document.createElement('span');
        label.id = 'mpv-pill-label';
        label.style.cssText = `
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #e2e8f0 !important;
        `;
        label.innerHTML = capturedStreamUrl ? '⚡ Stream Copied! (Ready for MPV / dl)' : '🎬 Click Play on Video';

        const copyBtn = document.createElement('button');
        copyBtn.id = 'mpv-pill-copy';
        copyBtn.innerHTML = '📋 Copy Link';
        copyBtn.style.cssText = `
            display: ${capturedStreamUrl ? 'inline-block' : 'none'} !important;
            padding: 6px 12px !important;
            background: linear-gradient(135deg, #059669, #10b981) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 12px !important;
            font-weight: 600 !important;
            cursor: pointer !important;
        `;
        copyBtn.onclick = () => {
            if (capturedStreamUrl) {
                copyStreamToClipboard(capturedStreamUrl);
                copyBtn.innerHTML = '✓ Copied!';
                setTimeout(() => { copyBtn.innerHTML = '📋 Copy Link'; }, 2000);
            }
        };

        pill.appendChild(label);
        pill.appendChild(copyBtn);
        targetRoot.appendChild(pill);
    }

    // Periodic check to survive SPA transitions & check <video> tag
    setInterval(() => {
        createPill();
        const v = document.querySelector('video');
        if (v && v.src) {
            handleStreamUrl(v.src);
        }
    }, 1000);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createPill);
    } else {
        createPill();
    }
})();
