param(
    [string]$BinDir = (Join-Path $env:USERPROFILE ".local\bin"),
    [string[]]$SkillRoots = @(".claude\skills", ".agents\skills"),
    [switch]$RemoveFromPath
)

$ErrorActionPreference = "Stop"

foreach ($file in @("phone_controller.py", "phone_controller_ocr.ps1", "phone-controller.cmd")) {
    $path = Join-Path $BinDir $file
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "removed $path"
    }
}

foreach ($root in $SkillRoots) {
    if ([System.IO.Path]::IsPathRooted($root)) {
        $dir = Join-Path $root "phone-controller"
    } else {
        $dir = Join-Path $env:USERPROFILE (Join-Path $root "phone-controller")
    }
    if (Test-Path -LiteralPath $dir) {
        Remove-Item -LiteralPath $dir -Recurse -Force
        Write-Host "removed $dir"
    }
}

if ($RemoveFromPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($userPath -split ";" | Where-Object { $_ -and ($_.TrimEnd("\") -ne $BinDir.TrimEnd("\")) })
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
    Write-Host "removed $BinDir from user PATH"
}

Write-Host "phone-controller uninstalled."
