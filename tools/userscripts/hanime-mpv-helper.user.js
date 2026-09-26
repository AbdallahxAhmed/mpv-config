// ==UserScript==
// @name         Hanime.tv MPV & Turbo Downloader Stream Grabber
// @namespace    https://github.com/AbdallahxAhmed/mpv-config
// @version      1.0
// @description  Intercepts Hanime video stream manifests and copies the direct M3U8 stream URL for MPV and turbo downloading
// @author       mpv-config
// @match        https://hanime.tv/videos/hentai/*
// @match        https://hanime.tv/hentai/video/*
// @grant        GM_setClipboard
// @grant        GM_notification
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let lastM3u8Url = null;

    // 1. Hook fetch and XMLHttpRequest to capture the signed manifest URL
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const url = (args[0] && typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url ? args[0].url : '');
        if (url && (url.includes('.m3u8') || url.includes('/manifest'))) {
            lastM3u8Url = url;
            updateButtonState(url);
        }
        return originalFetch.apply(this, args);
    };

    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        if (typeof url === 'string' && (url.includes('.m3u8') || url.includes('/manifest'))) {
            lastM3u8Url = url;
            updateButtonState(url);
        }
        return originalOpen.apply(this, [method, url, ...rest]);
    };

    // 2. Inject floating button into page UI
    function createButton() {
        if (document.getElementById('mpv-grabber-btn')) return;

        const btn = document.createElement('button');
        btn.id = 'mpv-grabber-btn';
        btn.innerHTML = '🎬 Copy MPV Stream';
        btn.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999999;
            padding: 12px 20px;
            background: linear-gradient(135deg, #7c3aed, #4f46e5);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            font-family: sans-serif;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
            transition: all 0.2s ease-in-out;
            display: flex;
            align-items: center;
            gap: 8px;
        `;

        btn.onmouseover = () => { btn.style.transform = 'translateY(-2px) scale(1.02)'; };
        btn.onmouseout = () => { btn.style.transform = 'translateY(0) scale(1)'; };

        btn.onclick = () => {
            if (!lastM3u8Url) {
                alert('Please start playing the video first so the stream manifest loads!');
                return;
            }
            if (typeof GM_setClipboard !== 'undefined') {
                GM_setClipboard(lastM3u8Url);
            } else {
                navigator.clipboard.writeText(lastM3u8Url);
            }
            btn.innerHTML = '✓ Stream Copied!';
            btn.style.background = 'linear-gradient(135deg, #059669, #10b981)';
            setTimeout(() => {
                btn.innerHTML = '🎬 Copy MPV Stream';
                btn.style.background = 'linear-gradient(135deg, #7c3aed, #4f46e5)';
            }, 3000);
        };

        document.body.appendChild(btn);
    }

    function updateButtonState(url) {
        const btn = document.getElementById('mpv-grabber-btn');
        if (btn) {
            btn.style.boxShadow = '0 0 20px rgba(124, 58, 237, 0.8)';
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createButton);
    } else {
        createButton();
    }
})();
