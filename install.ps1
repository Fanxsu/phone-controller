param(
    [string]$BinDir = (Join-Path $env:USERPROFILE ".local\bin"),
    [string[]]$SkillRoots = @(".claude\skills", ".agents\skills"),
    [switch]$AddToPath
)

$ErrorActionPreference = "Stop"
$source = $PSScriptRoot

function Find-Adb {
    $candidates = @()
    if ($env:ADB) { $candidates += $env:ADB }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    foreach ($key in @("ANDROID_HOME", "ANDROID_SDK_ROOT")) {
        $root = [Environment]::GetEnvironmentVariable($key)
        if ($root) { $candidates += (Join-Path $root "platform-tools\adb.exe") }
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe")
    }
    $candidates += "C:\dev\android-sdk\platform-tools\adb.exe"
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    return $null
}

$required = @("phone_controller.py", "phone_controller_ocr.ps1", "phone-controller.cmd", "SKILL.md")
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $file))) {
        throw "Missing $file in $source"
    }
}

$version = "unknown"
if (Test-Path -LiteralPath (Join-Path $source "VERSION")) {
    $version = (Get-Content -LiteralPath (Join-Path $source "VERSION") -Raw).Trim()
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    throw "Python 3.9+ not found. Install Python, then run install.ps1 again."
}

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
foreach ($file in @("phone_controller.py", "phone_controller_ocr.ps1", "phone-controller.cmd")) {
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $BinDir $file) -Force
}

foreach ($root in $SkillRoots) {
    if ([System.IO.Path]::IsPathRooted($root)) {
        $dest = Join-Path $root "phone-controller"
    } else {
        $dest = Join-Path $env:USERPROFILE (Join-Path $root "phone-controller")
    }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -LiteralPath (Join-Path $source "SKILL.md") -Destination $dest -Force
    if (Test-Path -LiteralPath (Join-Path $source "README.md")) {
        Copy-Item -LiteralPath (Join-Path $source "README.md") -Destination $dest -Force
    }
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathParts = @($userPath -split ";" | Where-Object { $_ })
$onPath = $pathParts | Where-Object { $_.TrimEnd("\") -ieq $BinDir.TrimEnd("\") }
if (-not $onPath) {
    if ($AddToPath) {
        $newPath = (($pathParts + $BinDir) -join ";")
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Added to user PATH: $BinDir"
        Write-Host "Open a new terminal for PATH changes to take effect."
    } else {
        Write-Warning "$BinDir is not on your user PATH."
        Write-Host "Add it with:"
        Write-Host ('  [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";' + $BinDir + '", "User")')
        Write-Host "Or re-run: .\install.ps1 -AddToPath"
    }
}

$adb = Find-Adb
if ($adb) {
    Write-Host "adb: $adb"
} else {
    Write-Warning "adb not found. Install Android platform-tools or set ANDROID_HOME / ANDROID_SDK_ROOT."
}

$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (Test-Path -LiteralPath $powershell) {
    $checkScript = @'
try {
    [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
    (([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) | ForEach-Object { $_.LanguageTag }) -join ','
} catch {
    'ERR:' + $_.Exception.Message
}
'@
    $languages = (& $powershell -NoProfile -Command $checkScript) -join "`n"
    if ([string]::IsNullOrWhiteSpace($languages) -or $languages.StartsWith("ERR:")) {
        Write-Warning "No Windows OCR language pack detected. OCR will fail until a language pack with OCR is installed."
        if ($languages) { Write-Host $languages }
    } else {
        Write-Host "OCR languages: $languages"
    }
} else {
    Write-Warning "Windows PowerShell 5.1 not found; OCR will not work."
}

Write-Host ""
Write-Host "phone-controller $version installed."
Write-Host "Verify:"
Write-Host "  phone-controller --version"
Write-Host "  phone-controller devices"
Write-Host "  phone-controller status"
Write-Host ""
Write-Host "If 'phone-controller' is not recognized, open a new terminal or add $BinDir to PATH."
