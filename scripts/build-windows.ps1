$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

Push-Location (Join-Path $PSScriptRoot '..')
try {
    python scripts/build_nuitka.py

    New-Item -ItemType Directory -Force artifacts | Out-Null
    $archive = 'PyOverScreen-windows-x64.zip'
    $archivePath = Join-Path artifacts $archive
    Compress-Archive -Path dist/PyOverScreen -DestinationPath $archivePath -Force
    $hash = (Get-FileHash $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$archivePath.sha256" -Value "$hash  $archive" -Encoding ascii
} finally {
    Pop-Location
}
