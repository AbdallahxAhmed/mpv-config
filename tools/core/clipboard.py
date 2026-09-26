"""
clipboard.py — Windows clipboard services and background change polling.
"""

import sys
import re
from typing import Optional


class ClipboardService:
    """Provides pure-Win32 clipboard access and URL detection with zero external dependencies."""

    @staticmethod
    def get_text() -> str:
        """Retrieve UTF-16 text directly from Windows clipboard."""
        if sys.platform != "win32":
            return ""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.OpenClipboard.argtypes = [wintypes.HWND]
            user32.OpenClipboard.restype = wintypes.BOOL
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = wintypes.BOOL
            user32.GetClipboardData.argtypes = [wintypes.UINT]
            user32.GetClipboardData.restype = wintypes.HANDLE
            kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalLock.restype = wintypes.LPVOID
            kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalUnlock.restype = wintypes.BOOL

            CF_UNICODETEXT = 13
            if not user32.OpenClipboard(None):
                return ""
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""

    @staticmethod
    def is_url(text: str) -> bool:
        """Check if text matches standard HTTP/HTTPS URL pattern."""
        if not text:
            return False
        clean = text.strip()
        return bool(re.match(r'^https?://[^\s/$.?#].[^\s]*$', clean, re.IGNORECASE))
