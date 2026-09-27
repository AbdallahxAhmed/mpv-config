// ==UserScript==
// @name         Hanime MPV Stream Grabber & Turbo Downloader
// @namespace    https://github.com/AbdallahxAhmed/mpv-config
// @version      4.0
// @description  Captures Hanime video stream manifests, auto-copies to Windows clipboard, and provides full 1-click MPV playback & turbo download controls
// @author       mpv-config
// @match        https://hanime.tv/*
// @match        https://*.hanime.tv/*
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
        return path.includes('/videos/hentai/') || path.includes('/hentai/video/') || path.includes('/playlists/');
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
            ta.style.left = '-9999px';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
            return true;
        } catch (_) {}
        return false;
    }

    // ─── AES-256-GCM Handshake Token Decryption (Web Crypto API) ─────────

    async function decryptXToken(tokenB64) {
        if (!tokenB64 || typeof tokenB64 !== 'string') return;
        try {
            const b64clean = tokenB64.replace(/-/g, '+').replace(/_/g, '/');
            const pad = b64clean.padEnd(b64clean.length + (4 - b64clean.length % 4) % 4, '=');
            const rawJson = JSON.parse(atob(pad));

            const b64toBuf = (s) => {
                const sc = s.replace(/-/g, '+').replace(/_/g, '/');
                const p = sc.padEnd(sc.length + (4 - sc.length % 4) % 4, '=');
                const bin = atob(p);
                const bytes = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                return bytes;
            };

            const hexToBuf = (hex) => {
                const bytes = new Uint8Array(hex.length / 2);
                for (let i = 0; i < hex.length; i += 2) bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
                return bytes;
            };

            const keyBytes = hexToBuf('5d657a4dcb0bad1c637ff2e221059b10ff17ae39fe855003e846918941f4ebe3');
            const iv = b64toBuf(rawJson.iv);
            const tag = b64toBuf(rawJson.tag);
            const data = b64toBuf(rawJson.data);
            const header = new TextEncoder().encode('htv-insecure-v1');

            // Web Crypto AES-GCM takes ciphertext concatenated with auth tag
            const combined = new Uint8Array(data.length + tag.length);
            combined.set(data, 0);
            combined.set(tag, data.length);

            const cryptoObj = (typeof window !== 'undefined' && window.crypto) || (typeof unsafeWindow !== 'undefined' && unsafeWindow.crypto);
            if (!cryptoObj || !cryptoObj.subtle) return;

            const cryptoKey = await cryptoObj.subtle.importKey(
                'raw', keyBytes, 'AES-GCM', false, ['decrypt']
            );

            const decrypted = await cryptoObj.subtle.decrypt(
                { name: 'AES-GCM', iv: iv, additionalData: header, tagLength: 128 },
                cryptoKey,
                combined
            );

            const manifest = JSON.parse(new TextDecoder().decode(decrypted));
            if (manifest && manifest.sources && Array.isArray(manifest.sources)) {
                for (const s of manifest.sources) {
                    if (s && s.src) {
                        const fullUrl = s.src.startsWith('http') ? s.src : `https://hanime.tv${s.src}`;
                        console.log('[Hanime MPV Grabber] Decrypted stream manifest from X-Token:', fullUrl);
                        onStreamCaptured(fullUrl);
                        break;
                    }
                }
            }
        } catch (err) {
            console.debug('[Hanime MPV Grabber] X-Token decryption notice:', err);
        }
    }

    // ─── Stream Capture Handler ──────────────────────────────────────────

    function onStreamCaptured(url) {
        if (!url || typeof url !== 'string') return;
        const lower = url.toLowerCase();
        const isMatch = lower.includes('.m3u8') || lower.includes('/manifest') || lower.includes('.mp4') ||
                        lower.includes('vids.hanime.tv') || lower.includes('weeb.hanime.tv');
        if (!isMatch) return;
        if (capturedStreamUrl === url) return;

        capturedStreamUrl = url;
        streamSlug = getSlug();
        console.log('[Hanime MPV Grabber] Stream Captured:', url);

        // 1. Immediately copy to Windows clipboard for MPV / terminal dl
        copyToClipboard(url);

        // 2. Silently dispatch to local daemon if running
        try {
            fetch(`${DAEMON_URL}/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    slug: streamSlug,
                    url: url,
                    title: document.title || streamSlug,
                    page_url: window.location.href,
                    cookies: document.cookie || ''
                }),
                mode: 'cors'
            }).catch(() => {});
        } catch (_) {}

        updatePillUI(true);
    }

    // ─── Main World Interception (Bypasses Sandbox & CSP) ────────────────

    const mainWorldCode = `
    (function() {
        if (window.__HANIME_MPV_HOOKED__) return;
        window.__HANIME_MPV_HOOKED__ = true;

        function notify(u) {
            if (!u || typeof u !== 'string') return;
            const l = u.toLowerCase();
            if (l.includes('.m3u8') || l.includes('/manifest') || l.includes('.mp4') || l.includes('vids.hanime.tv') || l.includes('weeb.hanime.tv')) {
                window.dispatchEvent(new CustomEvent('__MPV_STREAM_URL__', { detail: { url: u } }));
            }
        }

        function checkXToken(token) {
            if (token && typeof token === 'string' && token.length > 20) {
                window.dispatchEvent(new CustomEvent('__MPV_XTOKEN__', { detail: { token: token } }));
            }
        }

        // 1. Hook Fetch
        const _fetch = window.fetch;
        if (_fetch) {
            window.fetch = async function(...args) {
                try {
                    const reqUrl = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
                    notify(reqUrl);
                } catch (_) {}

                const response = await _fetch.apply(this, args);
                try {
                    if (response && response.url) notify(response.url);
                    if (response && response.headers) {
                        const token = response.headers.get('x-token') || response.headers.get('X-Token');
                        if (token) checkXToken(token);
                    }
                } catch (_) {}
                return response;
            };
        }

        // 2. Hook XMLHttpRequest
        const _open = window.XMLHttpRequest && window.XMLHttpRequest.prototype.open;
        const _send = window.XMLHttpRequest && window.XMLHttpRequest.prototype.send;
        if (_open) {
            window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                try {
                    const u = typeof url === 'string' ? url : (url && url.href ? url.href : String(url));
                    this.__mpvUrl = u;
                    notify(u);
                } catch (_) {}
                return _open.apply(this, [method, url, ...rest]);
            };
        }
        if (_send) {
            window.XMLHttpRequest.prototype.send = function(...args) {
                this.addEventListener('load', function() {
                    try {
                        const token = this.getResponseHeader('x-token') || this.getResponseHeader('X-Token');
                        if (token) checkXToken(token);
                        if (this.responseURL) notify(this.responseURL);
                    } catch (_) {}
                });
                return _send.apply(this, args);
            };
        }

        // 3. Hook HTMLMediaElement prototype
        const _play = HTMLMediaElement.prototype.play;
        if (_play) {
            HTMLMediaElement.prototype.play = function() {
                try {
                    if (this.src && !this.src.startsWith('blob:')) notify(this.src);
                    if (this.currentSrc && !this.currentSrc.startsWith('blob:')) notify(this.currentSrc);
                } catch (_) {}
                return _play.apply(this, arguments);
            };
        }

        // 4. Hook HTMLMediaElement src setter
        try {
            const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
            if (desc && desc.set) {
                const origSet = desc.set;
                desc.set = function(val) {
                    if (val && typeof val === 'string' && !val.startsWith('blob:')) notify(val);
                    return origSet.call(this, val);
                };
                Object.defineProperty(HTMLMediaElement.prototype, 'src', desc);
            }
        } catch (_) {}
    })();
    `;

    // Strategy A: Evaluate directly via unsafeWindow.eval (CSP 'unsafe-eval' compliant)
    try {
        const uWin = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
        if (uWin && uWin.eval) {
            uWin.eval(mainWorldCode);
        }
    } catch (_) {}

    // Strategy B: Inject script tag with nonce if available
    try {
        const script = document.createElement('script');
        const existingNonce = document.querySelector('script[nonce]');
        if (existingNonce) {
            const nonce = existingNonce.nonce || existingNonce.getAttribute('nonce');
            if (nonce) script.setAttribute('nonce', nonce);
        }
        script.textContent = mainWorldCode;
        (document.head || document.documentElement).appendChild(script);
        script.remove();
    } catch (_) {}

    // Strategy C: Direct hook on unsafeWindow / window
    try {
        const target = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
        if (target && !target.__HANIME_MPV_DIRECT_HOOK__) {
            target.__HANIME_MPV_DIRECT_HOOK__ = true;
            const tf = target.fetch;
            if (tf) {
                target.fetch = async function(...args) {
                    try {
                        const u = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
                        onStreamCaptured(u);
                    } catch (_) {}
                    const resp = await tf.apply(this, args);
                    try {
                        const tok = resp && resp.headers && (resp.headers.get('x-token') || resp.headers.get('X-Token'));
                        if (tok) decryptXToken(tok);
                    } catch (_) {}
                    return resp;
                };
            }
            const to = target.XMLHttpRequest && target.XMLHttpRequest.prototype.open;
            if (to) {
                target.XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                    try { onStreamCaptured(typeof url === 'string' ? url : String(url)); } catch (_) {}
                    return to.apply(this, [method, url, ...rest]);
                };
            }
        }
    } catch (_) {}

    // Listen for custom events from MAIN world hooks
    window.addEventListener('__MPV_STREAM_URL__', (e) => {
        if (e.detail && e.detail.url) onStreamCaptured(e.detail.url);
    });

    window.addEventListener('__MPV_XTOKEN__', (e) => {
        if (e.detail && e.detail.token) decryptXToken(e.detail.token);
    });

    // ─── DOM Scanner Fallback ─────────────────────────────────────────────

    function scanDOMForStreams() {
        // 1. Check video elements
        const videos = document.querySelectorAll('video');
        for (const v of videos) {
            if (v.src && !v.src.startsWith('blob:')) onStreamCaptured(v.src);
            if (v.currentSrc && !v.currentSrc.startsWith('blob:')) onStreamCaptured(v.currentSrc);
        }

        // 2. Check download links (e.g. MP4 download buttons/anchors)
        const downloadLinks = document.querySelectorAll('a[href*=".mp4"], a[href*=".m3u8"], a[download]');
        for (const a of downloadLinks) {
            if (a.href) onStreamCaptured(a.href);
        }

        // 3. Check Nuxt preloaded data if present
        try {
            const target = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
            if (target && target.__NUXT__) {
                const str = JSON.stringify(target.__NUXT__);
                const match = str.match(/https?:\/\/[^"'\s]+\.(?:m3u8|mp4)[^"'\s]*/i);
                if (match && match[0]) onStreamCaptured(match[0]);
            }
        } catch (_) {}
    }

    // ─── Floating Player Pill UI ──────────────────────────────────────────

    function updatePillUI(isReady) {
        const pill = document.getElementById('mpv-grabber-pill');
        if (!pill) return;

        const badge = document.getElementById('mpv-pill-status');
        const playBtn = document.getElementById('mpv-play-btn');
        const dlBtn = document.getElementById('mpv-dl-btn');
        const copyBtn = document.getElementById('mpv-copy-btn');

        if (isReady && capturedStreamUrl) {
            pill.style.border = '2px solid #10b981';
            pill.style.boxShadow = '0 0 35px rgba(16, 185, 129, 0.75)';
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
        playBtn.title = 'Copies direct stream & launches MPV player';
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

            if (!capturedStreamUrl) {
                playBtn.innerHTML = '▶ Play Video 1s First!';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2200);
                return;
            }

            fetch(`${DAEMON_URL}/play`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            }).then(() => {
                playBtn.innerHTML = '✓ Playing in MPV!';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2500);
            }).catch(() => {
                playBtn.innerHTML = '✓ Copied! (Open MPV & Ctrl+V)';
                setTimeout(() => { playBtn.innerHTML = '🎬 Play in MPV'; }, 2500);
            });
        };

        // 3. 16x Turbo Download Button
        const dlBtn = document.createElement('button');
        dlBtn.id = 'mpv-dl-btn';
        dlBtn.innerHTML = '⚡ Turbo Download';
        dlBtn.title = 'Copies direct stream link for terminal turbo downloading';
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

            if (!capturedStreamUrl) {
                dlBtn.innerHTML = '▶ Play Video 1s First!';
                setTimeout(() => { dlBtn.innerHTML = '⚡ Turbo Download'; }, 2200);
                return;
            }

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
        copyBtn.title = 'Copy stream or page URL to clipboard';
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

    // ─── Polling & Lifecycle ─────────────────────────────────────────────

    setInterval(() => {
        createFullPill();
        scanDOMForStreams();
    }, 800);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            createFullPill();
            scanDOMForStreams();
        });
    } else {
        createFullPill();
        scanDOMForStreams();
    }
})();
