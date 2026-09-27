// ==UserScript==
// @name         Hanime MPV Stream Grabber & Turbo Downloader
// @namespace    https://github.com/AbdallahxAhmed/mpv-config
// @version      3.5
// @description  Captures Hanime video stream manifests, auto-copies to Windows clipboard, and provides full 1-click MPV playback & turbo download controls
// @author       mpv-config
// @match        https://hanime.tv/*
// @grant        GM_setClipboard
// @grant        unsafeWindow
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

    function copyToClipboard(text) {
        if (!text) return false;
        try {
            if (typeof GM_setClipboard !== 'undefined') {
                GM_setClipboard(text);
                return true;
            }
        } catch (_) {}
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
                return true;
            }
        } catch (_) {}
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
            return true;
        } catch (_) {}
        return false;
    }

    // ─── Core Stream Interception ────────────────────────────────────────

    function onStreamCaptured(url) {
        if (!url || typeof url !== 'string') return;
        if (!url.includes('.m3u8') && !url.includes('/manifest') && !url.includes('.mp4')) return;
        if (capturedStreamUrl === url) return;

        capturedStreamUrl = url;
        streamSlug = getSlug();
        console.log('[Hanime MPV Grabber] Successfully intercepted stream manifest:', url);

        // 1. Immediately copy to Windows clipboard for MPV / terminal dl
        copyToClipboard(url);

        // 2. Silently dispatch to local daemon if running
        try {
            const payload = JSON.stringify({
                slug: streamSlug,
                url: url,
                title: document.title || streamSlug,
                page_url: window.location.href,
                cookies: document.cookie || ''
            });
            fetch(`${DAEMON_URL}/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                mode: 'cors'
            }).catch(() => {});
        } catch (_) {}

        updatePillUI(true);
    }

    // ─── Injection into MAIN World (Bypasses Tampermonkey Sandbox) ────────

    function injectMainWorldHooks() {
        const code = `
        (function() {
            function report(u) {
                if (!u || typeof u !== 'string') return;
                if (u.includes('.m3u8') || u.includes('/manifest') || u.includes('.mp4') || u.includes('vids.hanime.tv') || u.includes('weeb.hanime.tv')) {
                    window.dispatchEvent(new CustomEvent('HANIME_MPV_STREAM', { detail: { url: u } }));
                }
            }

            // Hook window.fetch in Main Page World
            const _fetch = window.fetch;
            if (_fetch) {
                window.fetch = async function(...args) {
                    try {
                        const target = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
                        report(target);
                    } catch (_) {}
                    return _fetch.apply(this, args);
                };
            }

            // Hook XMLHttpRequest in Main Page World
            const _open = window.XMLHttpRequest && window.XMLHttpRequest.prototype.open;
            if (_open) {
                window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                    try { report(url); } catch (_) {}
                    return _open.apply(this, [method, url, ...rest]);
                };
            }
        })();
        `;
        const script = document.createElement('script');
        script.textContent = code;
        (document.head || document.documentElement).appendChild(script);
        script.remove();
    }

    // Listen for custom event from MAIN page world
    window.addEventListener('HANIME_MPV_STREAM', (e) => {
        if (e.detail && e.detail.url) {
            onStreamCaptured(e.detail.url);
        }
    });

    // Also hook unsafeWindow directly if accessible
    function hookUnsafeWindow() {
        const target = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
        if (!target) return;

        try {
            const f = target.fetch;
            if (f) {
                target.fetch = async function(...args) {
                    try {
                        const u = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
                        onStreamCaptured(u);
                    } catch (_) {}
                    return f.apply(this, args);
                };
            }
            const o = target.XMLHttpRequest && target.XMLHttpRequest.prototype.open;
            if (o) {
                target.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                    try { onStreamCaptured(url); } catch (_) {}
                    return o.apply(this, [method, url, ...rest]);
                };
            }
        } catch (_) {}
    }

    // Check Nuxt.js preloaded state
    function scanNuxtState() {
        try {
            const target = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
            if (!target || !target.__NUXT__) return;
            const str = JSON.stringify(target.__NUXT__);
            const matches = str.match(/https?:\/\/[^"'\s]+\.(?:m3u8|mp4)[^"'\s]*/gi);
            if (matches && matches.length > 0) {
                for (const m of matches) {
                    if (m.includes('.m3u8') || m.includes('.mp4')) {
                        onStreamCaptured(m);
                        break;
                    }
                }
            }
        } catch (_) {}
    }

    // ─── Full Control Pill UI ─────────────────────────────────────────────

    function updatePillUI(isReady) {
        const pill = document.getElementById('mpv-grabber-pill');
        if (!pill) return;

        const badge = document.getElementById('mpv-pill-status');
        const playBtn = document.getElementById('mpv-play-btn');
        const dlBtn = document.getElementById('mpv-dl-btn');
        const copyBtn = document.getElementById('mpv-copy-btn');

        if (isReady && capturedStreamUrl) {
            pill.style.border = '2px solid #10b981';
            pill.style.boxShadow = '0 0 30px rgba(16, 185, 129, 0.7)';
            if (badge) {
                badge.innerHTML = '⚡ Stream Ready (Copied)';
                badge.style.color = '#34d399';
            }
            if (playBtn) playBtn.style.opacity = '1';
            if (dlBtn) dlBtn.style.opacity = '1';
            if (copyBtn) copyBtn.style.opacity = '1';
        } else {
            pill.style.border = '2px solid #7c3aed';
            pill.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.85)';
            if (badge) {
                badge.innerHTML = '🎬 Play Video to Grab Stream';
                badge.style.color = '#cbd5e1';
            }
        }
    }

    function createFullPill() {
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
            background: rgba(15, 23, 42, 0.95) !important;
            border: 2px solid ${capturedStreamUrl ? '#10b981' : '#7c3aed'} !important;
            border-radius: 14px !important;
            padding: 8px 14px !important;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.85) !important;
            backdrop-filter: blur(10px) !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            color: #ffffff !important;
            user-select: none !important;
            transition: all 0.3s ease !important;
        `;

        // 1. Status Indicator
        const badge = document.createElement('span');
        badge.id = 'mpv-pill-status';
        badge.style.cssText = `
            font-size: 13px !important;
            font-weight: 600 !important;
            color: ${capturedStreamUrl ? '#34d399' : '#cbd5e1'} !important;
            white-space: nowrap !important;
        `;
        badge.innerHTML = capturedStreamUrl ? '⚡ Stream Ready (Copied)' : '🎬 Play Video to Grab Stream';

        // 2. Play in MPV Button
        const playBtn = document.createElement('button');
        playBtn.id = 'mpv-play-btn';
        playBtn.innerHTML = '🎬 Play in MPV';
        playBtn.title = 'Copies stream & plays in MPV player';
        playBtn.style.cssText = `
            padding: 7px 13px !important;
            background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            cursor: pointer !important;
            white-space: nowrap !important;
            transition: all 0.2s !important;
        `;
        playBtn.onclick = () => {
            const url = capturedStreamUrl || window.location.href;
            copyToClipboard(url);

            // Silent request to local daemon if present
            fetch(`${DAEMON_URL}/play`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            }).then(() => {
                playBtn.innerHTML = '✓ Playing in MPV!';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2500);
            }).catch(() => {
                // Daemon not running - inform user cleanly on the button
                playBtn.innerHTML = '✓ Copied! (Ctrl+V in MPV)';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2500);
            });
        };

        // 3. 16x Turbo Download Button
        const dlBtn = document.createElement('button');
        dlBtn.id = 'mpv-dl-btn';
        dlBtn.innerHTML = '⚡ Turbo Download';
        dlBtn.title = 'Copies stream link for turbo downloading';
        dlBtn.style.cssText = `
            padding: 7px 13px !important;
            background: linear-gradient(135deg, #059669, #10b981) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            cursor: pointer !important;
            white-space: nowrap !important;
            transition: all 0.2s !important;
        `;
        dlBtn.onclick = () => {
            const url = capturedStreamUrl || window.location.href;
            copyToClipboard(url);

            fetch(`${DAEMON_URL}/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            }).then(() => {
                dlBtn.innerHTML = '✓ Download Started!';
                setTimeout(() => { dlBtn.innerHTML = '⚡ Turbo Download'; }, 2500);
            }).catch(() => {
                dlBtn.innerHTML = '✓ Copied! (Run dl in terminal)';
                setTimeout(() => { dlBtn.innerHTML = '⚡ Turbo Download'; }, 2500);
            });
        };

        // 4. Copy Link Button
        const copyBtn = document.createElement('button');
        copyBtn.id = 'mpv-copy-btn';
        copyBtn.innerHTML = '📋 Copy Link';
        copyBtn.title = 'Copy direct stream URL to clipboard';
        copyBtn.style.cssText = `
            padding: 7px 11px !important;
            background: rgba(255, 255, 255, 0.1) !important;
            color: #e2e8f0 !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            border-radius: 8px !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            cursor: pointer !important;
            white-space: nowrap !important;
            transition: all 0.2s !important;
        `;
        copyBtn.onclick = () => {
            const url = capturedStreamUrl || window.location.href;
            copyToClipboard(url);
            copyBtn.innerHTML = '✓ Copied!';
            setTimeout(() => { copyBtn.innerHTML = '📋 Copy Link'; }, 2000);
        };

        pill.appendChild(badge);
        pill.appendChild(playBtn);
        pill.appendChild(dlBtn);
        pill.appendChild(copyBtn);
        targetRoot.appendChild(pill);
    }

    // Initialize injection
    injectMainWorldHooks();
    hookUnsafeWindow();

    // Polling loop: checks DOM elements, Nuxt state, and ensures UI remains visible
    setInterval(() => {
        createFullPill();
        scanNuxtState();

        // Check HTML5 video tag
        const v = document.querySelector('video');
        if (v && v.src && !v.src.startsWith('blob:')) {
            onStreamCaptured(v.src);
        }
    }, 1000);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            injectMainWorldHooks();
            createFullPill();
        });
    } else {
        createFullPill();
    }
})();
