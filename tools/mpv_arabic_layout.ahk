#Requires AutoHotkey v2.0
#SingleInstance Force

; Clean exit 2 seconds after mpv closes (no orphan background processes)
SetTimer(WatchMpv, 2000)
WatchMpv() {
    if !ProcessExist("mpv.exe")
        ExitApp()
}

; Check if the active window's thread layout is Arabic / non-Latin
IsArabic() {
    hwnd := WinActive("ahk_exe mpv.exe")
    if !hwnd
        return false
    threadId := DllCall("GetWindowThreadProcessId", "Ptr", hwnd, "Ptr", 0, "UInt")
    if !threadId
        return false
    layout := DllCall("GetKeyboardLayout", "UInt", threadId, "UPtr")
    primaryLang := layout & 0x3FF
    return primaryLang == 0x01 || ((layout & 0xFFFF) != 0x0409 && primaryLang != 0x09)
}

#HotIf WinActive("ahk_exe mpv.exe") and IsArabic()

; Number row / tilde
SC029::Send("{Blind}``")

; Top letter row: Q - ]
SC010::Send("{Blind}q")
SC011::Send("{Blind}w")
SC012::Send("{Blind}e")
SC013::Send("{Blind}r")
SC014::Send("{Blind}t")
SC015::Send("{Blind}y")
SC016::Send("{Blind}u")
SC017::Send("{Blind}i")
SC018::Send("{Blind}o")
SC019::Send("{Blind}p")
SC01A::Send("{Blind}[")
SC01B::Send("{Blind}]")

; Home letter row: A - '
SC01E::Send("{Blind}a")
SC01F::Send("{Blind}s")
SC020::Send("{Blind}d")
SC021::Send("{Blind}f")
SC022::Send("{Blind}g")
SC023::Send("{Blind}h")
SC024::Send("{Blind}j")
SC025::Send("{Blind}k")
SC026::Send("{Blind}l")
SC027::Send("{Blind};")
SC028::Send("{Blind}'")

; Bottom letter row: Z - /
SC02C::Send("{Blind}z")
SC02D::Send("{Blind}x")
SC02E::Send("{Blind}c")
SC02F::Send("{Blind}v")
SC030::Send("{Blind}b")
SC031::Send("{Blind}n")
SC032::Send("{Blind}m")
SC033::Send("{Blind},")
SC034::Send("{Blind}.")
SC035::Send("{Blind}/")
