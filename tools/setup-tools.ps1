# Download the two third-party tools the build scripts need into tools\ (git-ignored):
#   - freerouting 2.5.0 (GPL-3.0) jar      https://github.com/freerouting/freerouting
#   - Eclipse Temurin 25 JRE (portable zip) https://adoptium.net
# Nothing is installed system-wide and PATH is not touched. Every download is checked
# against a pinned SHA-256; a mismatch stops the script and deletes the file.
#
# Why the jar and not freerouting's native CLI: freerouting-cli 2.5.0 crashes on the first
# board snapshot for KiCad 10 DSN files (freerouting/freerouting#957). The jar is compiled
# for Java 25 (class file 69), hence the bundled JRE.
#   powershell -ExecutionPolicy Bypass -File tools\setup-tools.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with the progress bar
Set-Location $PSScriptRoot

function Get-Verified($url, $file, $sha256) {
    if ((Test-Path $file) -and ((Get-FileHash $file -Algorithm SHA256).Hash -eq $sha256.ToUpper())) {
        Write-Host "ok (cached)  $file"
        return
    }
    Write-Host "downloading  $url"
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
    $got = (Get-FileHash $file -Algorithm SHA256).Hash
    if ($got -ne $sha256.ToUpper()) {
        Remove-Item $file
        throw "SHA-256 mismatch for $file`n  expected $sha256`n  got      $got"
    }
    Write-Host "ok (verified) $file"
}

New-Item -ItemType Directory -Force freerouting, jre | Out-Null

Get-Verified 'https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar' `
    'freerouting\freerouting-2.5.0.jar' 'f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7'

$jreZip = 'jre\OpenJDK25U-jre_x64_windows_hotspot_25.0.4.1_1.zip'
Get-Verified 'https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jre_x64_windows_hotspot_25.0.4.1_1.zip' `
    $jreZip '4c95451cea98556def2c54f7782933f52a26d4a36bd85e1d59f0364464828b07'
if (-not (Get-ChildItem 'jre\*\bin\java.exe' -ErrorAction SilentlyContinue)) {
    Expand-Archive $jreZip -DestinationPath jre
}
& (Get-ChildItem 'jre\*\bin\java.exe' | Select-Object -First 1).FullName -version
