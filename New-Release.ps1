param(
    [ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$')][string]$Version='v0.6.0-preview',
    [string]$PayloadPath=(Join-Path $PSScriptRoot 'build\payload')
)
$ErrorActionPreference='Stop'
$payload=(Resolve-Path -LiteralPath $PayloadPath).Path
$m=Get-Content -LiteralPath (Join-Path $payload 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($m.pak -ne 'pakchunk99-PCM2026ZH_P.pak'){throw 'Unexpected pak filename'}
foreach($entry in @(@('GameCyclingDLL_Master.dll',$m.dll_after),@($m.pak,$m.sha256))){
    if((Get-FileHash -LiteralPath (Join-Path $payload $entry[0]) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry[1]){throw ('Payload mismatch: '+$entry[0])}
}
$dist=Join-Path $PSScriptRoot 'build\releases'
$name='PCM26-ZH-'+$Version
$folder=Join-Path $dist $name
$zip=Join-Path $dist ($name+'.zip')
if((Test-Path -LiteralPath $folder) -or (Test-Path -LiteralPath $zip)){throw 'Version already packaged; choose a new version or move previous output'}
New-Item -ItemType Directory -Force -Path (Join-Path $folder 'payload') | Out-Null
foreach($file in @('Install.ps1','Launcher.ps1','Install.cmd','Check.cmd','Uninstall.cmd','Recover.cmd','Repair.cmd','README.md','LICENSE','THIRD_PARTY.md','CHANGELOG.md')){
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $folder
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'docs') -Destination $folder -Recurse
foreach($file in @('manifest.json','GameCyclingDLL_Master.dll',$m.pak)){
    Copy-Item -LiteralPath (Join-Path $payload $file) -Destination (Join-Path $folder 'payload')
}
$m | Add-Member -NotePropertyName release_version -NotePropertyValue $Version -Force
$m | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $folder 'payload\manifest.json') -Encoding UTF8
foreach($entry in @(@('GameCyclingDLL_Master.dll',$m.dll_after),@($m.pak,$m.sha256))){
    if((Get-FileHash -LiteralPath (Join-Path (Join-Path $folder 'payload') $entry[0]) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry[1]){throw ('Staged payload changed during packaging: '+$entry[0])}
}
Compress-Archive -LiteralPath $folder -DestinationPath $zip -CompressionLevel Optimal
$digest=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText(($zip+'.sha256'),($digest+'  '+[IO.Path]::GetFileName($zip)+"`n"),[Text.UTF8Encoding]::new($false))
Write-Host ('Release ZIP: '+$zip)
Write-Host ('SHA256: '+$digest)
