/**
 * MPV Media & Cookie Companion — Background Service Worker
 * 
 * Auto-syncs Cloudflare clearance & auth cookies to %APPDATA%/yt-dlp/cookies.txt
 * Intercepts signed HLS / M3U8 video streams
 * Provides 1-click "Play in MPV" and "Download Video" right-click context menus
 */

const NATIVE_HOST = "com.mpv.cookiesync";
const LOG_PREFIX = "[MPV Companion]";

// ─── Native Messaging Wrapper ─────────────────────────────────────────

function sendToNativeHost(message) {
    try {
        chrome.runtime.sendNativeMessage(NATIVE_HOST, message, (response) => {
            if (chrome.runtime.lastError) {
                // Native host may not be installed or browser just launched
                console.debug(`${LOG_PREFIX} Native host notice:`, chrome.runtime.lastError.message);
            } else if (response && response.status === "ok") {
                console.log(`${LOG_PREFIX} Native host success:`, response);
            }
        });
    } catch (err) {
        console.debug(`${LOG_PREFIX} Send error:`, err);
    }
}

// ─── Cookie Formatting & Sync ─────────────────────────────────────────

function formatNetscapeCookies(cookies) {
    const lines = [
        "# Netscape HTTP Cookie File",
        "# Exported automatically by MPV Companion Extension",
        ""
    ];
    for (const c of cookies) {
        const domain = c.domain.startsWith(".") ? c.domain : "." + c.domain;
        const flag = "TRUE";
        const path = c.path || "/";
        const secure = c.secure ? "TRUE" : "FALSE";
        const expiry = c.expirationDate ? Math.round(c.expirationDate) : 0;
        lines.push(`${domain}\t${flag}\t${path}\t${secure}\t${expiry}\t${c.name}\t${c.value}`);
    }
    return lines.join("\n") + "\n";
}

async function syncDomainCookies(domain) {
    if (!chrome.cookies) return;
    try {
        // Collect domain cookies + auth subdomain cookies
        const domains = [domain];
        if (domain.includes("hanime.tv")) {
            domains.push("auth.hanime.tv");
        }

        const allCookies = [];
        for (const d of domains) {
            const list = await chrome.cookies.getAll({ domain: d });
            if (list && list.length > 0) {
                allCookies.push(...list);
            }
        }

        if (allCookies.length === 0) return;

        const netscapeText = formatNetscapeCookies(allCookies);
        const userAgent = navigator.userAgent;

        // 1. Send via Native Messaging
        sendToNativeHost({
            action: "sync_cookies",
            domain: domain,
            cookies: netscapeText,
            user_agent: userAgent
        });

        // 2. Send via local HTTP daemon (fallback / dual-sync)
        fetch("http://127.0.0.1:8765/sync", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                domain: domain,
                cookies: netscapeText,
                user_agent: userAgent
            })
        }).catch(() => {});
    } catch (err) {
        console.warn(`${LOG_PREFIX} Cookie sync error for ${domain}:`, err);
    }
}

// ─── Tab Navigation Watcher ───────────────────────────────────────────

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.url) {
        try {
            const u = new URL(tab.url);
            const domain = u.hostname.toLowerCase();
            if (domain.includes("hanime.tv") || domain.includes("perverzija.com")) {
                syncDomainCookies(domain);
            }
        } catch (_) {}
    }
});

// ─── Stream Interception ──────────────────────────────────────────────

const capturedStreams = new Map(); // tabId -> m3u8 url

if (chrome.webRequest && chrome.webRequest.onBeforeRequest) {
    chrome.webRequest.onBeforeRequest.addListener(
        (details) => {
            const url = details.url;
            if (url && (url.includes(".m3u8") || url.includes("/manifest")) && !url.includes("google")) {
                if (details.tabId > 0) {
                    capturedStreams.set(details.tabId, url);
                    try {
                        chrome.tabs.get(details.tabId, (tab) => {
                            const pageUrl = tab ? tab.url : "";
                            const title = tab ? tab.title : "";
                            let slug = "";
                            if (pageUrl) {
                                slug = pageUrl.split("/").filter(Boolean).pop();
                            }
                            sendToNativeHost({
                                action: "stream_captured",
                                slug: slug,
                                url: url,
                                title: title,
                                page_url: pageUrl
                            });
                            fetch("http://127.0.0.1:8765/stream", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    slug: slug,
                                    url: url,
                                    title: title,
                                    page_url: pageUrl
                                })
                            }).catch(() => {});
                        });
                    } catch (_) {}
                }
            }
        },
        { urls: ["*://*/*.m3u8*", "*://*/manifest*"] }
    );
}

// ─── Context Menu ─────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: "mpv-play",
        title: "🎬 Play in MPV",
        contexts: ["page", "video", "link"]
    });

    chrome.contextMenus.create({
        id: "mpv-download",
        title: "⚡ Download Video (yt-dlp Turbo)",
        contexts: ["page", "video", "link"]
    });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    const rawTarget = info.linkUrl || info.srcUrl || info.pageUrl || (tab && tab.url);
    if (!rawTarget) return;

    // Check if we captured a direct M3U8 stream for this tab
    const m3u8 = tab ? capturedStreams.get(tab.id) : null;
    const targetUrl = m3u8 || rawTarget;

    try {
        const u = new URL(rawTarget);
        await syncDomainCookies(u.hostname.toLowerCase());
    } catch (_) {}

    if (info.menuItemId === "mpv-play") {
        sendToNativeHost({
            action: "play",
            url: targetUrl,
            raw_page_url: rawTarget,
            user_agent: navigator.userAgent
        });
    } else if (info.menuItemId === "mpv-download") {
        sendToNativeHost({
            action: "download",
            url: targetUrl,
            raw_page_url: rawTarget,
            user_agent: navigator.userAgent
        });
    }
});
