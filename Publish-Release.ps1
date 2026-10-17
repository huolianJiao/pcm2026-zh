param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')][string]$Repository,
    [ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$')][string]$Version='v0.6.0-preview'
)
$ErrorActionPreference='Stop'
$zip=Join-Path $PSScriptRoot ('build\releases\PCM26-ZH-'+$Version+'.zip')
$checksum=$zip+'.sha256'
if(!(Test-Path -LiteralPath $zip) -or !(Test-Path -LiteralPath $checksum)){throw 'Run New-Release.ps1 first'}
$expected=(Get-Content -LiteralPath $checksum -Raw).Split(' ')[0]
if((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected){throw 'Release ZIP checksum mismatch'}
Get-Command gh -ErrorAction Stop | Out-Null
# Requires an existing pushed tag. No implicit commit, tag, or public publication.
$arguments=@('release','create',$Version,$zip,$checksum,'--repo',$Repository,'--verify-tag','--draft','--title',('PCM26 中文汉化 '+$Version),'--notes-file',(Join-Path $PSScriptRoot 'docs\RELEASE_NOTES.md'))
if($Version.Contains('-')){$arguments+='--prerelease'}
& gh @arguments
if($LASTEXITCODE -ne 0){throw 'GitHub release creation failed; inspect gh output'}
Write-Host 'Draft created with installer ZIP and checksum. Review it on GitHub before publishing.'
