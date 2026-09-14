param(
    [Parameter(Mandatory=$true)]
    [string]$Action
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class JarvisWindow {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}
"@

$map = @{
    "chrome"     = @("chrome")
    "google"     = @("chrome")
    "firefox"    = @("firefox")
    "edge"       = @("msedge")
    "discord"    = @("discord")
    "steam"      = @("steam")
    "notepad"    = @("notepad")
    "блокнот"    = @("notepad")
    "calculator" = @("calculator", "calc")
    "калькулятор"= @("calculator", "calc")
    "explorer"   = @("explorer")
    "проводник"  = @("explorer")
}

$targets = $map[$Action.ToLowerInvariant()]
if (-not $targets) {
    exit 2
}

$handles = New-Object System.Collections.Generic.List[System.IntPtr]
$callback = [JarvisWindow+EnumWindowsProc] {
    param([IntPtr]$hWnd, [IntPtr]$lParam)
    if (-not [JarvisWindow]::IsWindowVisible($hWnd)) { return $true }
    [uint32]$pid = 0
    [void][JarvisWindow]::GetWindowThreadProcessId($hWnd, [ref]$pid)
    try {
        $name = (Get-Process -Id $pid -ErrorAction Stop).ProcessName.ToLowerInvariant()
        if ($targets -contains $name) {
            $handles.Add($hWnd)
        }
    } catch {}
    return $true
}

[void][JarvisWindow]::EnumWindows($callback, [IntPtr]::Zero)

foreach ($handle in $handles) {
    [void][JarvisWindow]::ShowWindow($handle, 6)
}
exit 0
