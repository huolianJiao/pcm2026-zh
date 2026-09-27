param([ValidateSet('Install','Check','Uninstall','Recover')][string]$Mode='Install')
$ErrorActionPreference='Stop'
try {
    $roots=@()
    foreach($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')){
        $reg=Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if($reg){if($reg.SteamPath){$roots+=$reg.SteamPath};if($reg.InstallPath){$roots+=$reg.InstallPath}}
    }
    $libraries=@($roots)
    foreach($root in $roots){
        $vdf=Join-Path $root 'steamapps\libraryfolders.vdf'
        if(Test-Path -LiteralPath $vdf){
            $text=Get-Content -LiteralPath $vdf -Raw -Encoding UTF8
            foreach($match in [regex]::Matches($text,'"path"\s+"([^"]+)"')){$libraries+=$match.Groups[1].Value.Replace('\\','\')}
        }
    }
    $found=@($libraries | Select-Object -Unique | ForEach-Object {
        $candidate=Join-Path $_ 'steamapps\common\Pro Cycling Manager 2026'
        if(Test-Path -LiteralPath (Join-Path $candidate 'PCM\Binaries\Win64\GameCyclingDLL_Master.dll')){$candidate}
    })
    $game=''
    if($found.Count -eq 1){
        Write-Host ('Found game: '+$found[0])
        if((Read-Host 'Use this folder? [Y/n]') -notmatch '^[nN]'){$game=$found[0]}
    }
    if(!$game){$game=(Read-Host 'Paste PCM2026 install folder (no quotes needed)').Trim().Trim('"')}
    & (Join-Path $PSScriptRoot 'Install.ps1') -GamePath $game -Mode $Mode -PayloadPath (Join-Path $PSScriptRoot 'payload')
} catch {Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red;exit 1}
