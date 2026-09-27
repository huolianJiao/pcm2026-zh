param(
 [Parameter(Mandatory=$true)][string]$GamePath,
 [ValidateSet('Install','Check','Uninstall','Recover')][string]$Mode='Install',
 [string]$PayloadPath=(Join-Path $PSScriptRoot 'build\payload')
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Hash([string]$p) {
 $s=[IO.File]::OpenRead($p);$a=[Security.Cryptography.SHA256]::Create()
 try {([BitConverter]::ToString($a.ComputeHash($s))).Replace('-','').ToLowerInvariant()}
 finally {$s.Dispose();$a.Dispose()}
}
function Plain([string]$path) {
 $p=[IO.Path]::GetFullPath($path)
 while($p){
  if(Test-Path -LiteralPath $p){if(([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw ('Linked/junction path unsupported: '+$p)}}
  $parent=[IO.Path]::GetDirectoryName($p);if($p -eq $parent){break};$p=$parent
 }
}
function Current([string]$p) {if(Test-Path -LiteralPath $p){Hash $p}else{'absent'}}
function AtomicCopy([string]$source,[string]$dest,[string]$expected) {
 Plain $source;Plain $dest
 if((Hash $source) -ne $expected){throw ('Source hash mismatch: '+$source)}
 $temp=$dest+'.pcm26-'+[Guid]::NewGuid().ToString('N')+'.tmp'
 [IO.File]::Copy($source,$temp,$false)
 $f=[IO.File]::Open($temp,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {$f.Flush($true)} finally {$f.Dispose()}
 if((Hash $temp) -ne $expected){throw 'Staged file hash mismatch'}
 if(Test-Path -LiteralPath $dest){[IO.File]::Replace($temp,$dest,[NullString]::Value)}else{[IO.File]::Move($temp,$dest)}
 if((Hash $dest) -ne $expected){throw ('Target hash mismatch: '+$dest)}
}
function AtomicJson($object,[string]$dest) {
 Plain $dest;$temp=$dest+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
 [IO.File]::WriteAllText($temp,($object | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
 $f=[IO.File]::Open($temp,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {$f.Flush($true)} finally {$f.Dispose()}
 if(Test-Path -LiteralPath $dest){[IO.File]::Replace($temp,$dest,[NullString]::Value)}else{[IO.File]::Move($temp,$dest)}
}
function Closed {if(Get-Process -Name 'PCM-Win64-Shipping' -ErrorAction SilentlyContinue){throw 'Save and close PCM2026 first'}}
function Manifest($m) {
 if($m.pak -ne 'pakchunk99-PCM2026ZH_P.pak'){throw 'Unexpected pak filename'}
 foreach($h in @($m.dll_before,$m.dll_after,$m.sha256)){if($h -cnotmatch '^[a-f0-9]{64}$'){throw 'Invalid manifest hash'}}
}
$game=[IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GamePath).Path)
$dll=Join-Path $game 'PCM\Binaries\Win64\GameCyclingDLL_Master.dll'
$pak=Join-Path $game 'PCM\Content\Paks\pakchunk99-PCM2026ZH_P.pak'
$backup=Join-Path $game 'PCM26-ZH-Backup'
$original=Join-Path $backup 'GameCyclingDLL_Master.original.dll'
$statePath=Join-Path $backup 'installed.json'
$pending=Join-Path $backup 'pending.json'
$lockPath=Join-Path $backup 'installer.lock'
foreach($p in @($dll,$pak,$backup,$original,$statePath,$pending,$lockPath)){Plain $p}
if(!(Test-Path -LiteralPath $dll -PathType Leaf) -or !(Test-Path -LiteralPath (Split-Path $pak) -PathType Container)){throw 'Not a PCM2026 installation folder'}

# Journal recovery never needs the downloaded payload and never replaces unknown files.
function Rollback {
 Closed
 $j=Get-Content -LiteralPath $pending -Raw -Encoding UTF8 | ConvertFrom-Json
 if($j.transaction -cnotmatch '^txn-[a-f0-9]{32}$' -or $j.game -ne $game){throw 'Invalid recovery journal'}
 $dir=Join-Path $backup $j.transaction;Plain $dir
 $items=@(@('dll',$dll,'before.dll'),@('pak',$pak,'before.pak'),@('state',$statePath,'before.json'))
 foreach($item in $items){
  $key=$item[0];$before=$j.before.$key;$after=$j.after.$key
  foreach($h in @($before,$after)){if($h -cnotmatch '^(absent|[a-f0-9]{64})$'){throw 'Invalid recovery hash'}}
  Plain $item[1]
  if((Current $item[1]) -notin @($before,$after)){throw ('Recovery refused: external change: '+$item[1])}
  if($before -ne 'absent'){
   $saved=Join-Path $dir $item[2];Plain $saved
   if((Hash $saved) -ne $before){throw ('Recovery backup damaged: '+$saved)}
  }
 }
 foreach($item in $items){
  $before=$j.before.($item[0]);$dest=$item[1]
  if((Current $dest) -eq $before){continue}
  if($before -eq 'absent'){[IO.File]::Move($dest,(Join-Path $dir ('rollback-'+$item[0]+'-'+[Guid]::NewGuid().ToString('N'))))}
  else{AtomicCopy (Join-Path $dir $item[2]) $dest $before}
 }
 foreach($item in $items){if((Current $item[1]) -ne $j.before.($item[0])){throw 'Rollback verification failed'}}
 [IO.File]::Move($pending,(Join-Path $dir 'rolled-back.json'))
 Write-Host 'Previous state restored and verified. Backups retained.'
}
if($Mode -ne 'Check'){Closed}
[IO.Directory]::CreateDirectory($backup) | Out-Null
$lock=$null
try {
 try {$lock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
 catch {throw 'Installer already running, or backup directory not writable'}
 if($Mode -eq 'Recover'){
  if(!(Test-Path -LiteralPath $pending)){Write-Host 'No interrupted transaction.';exit}
  Rollback;exit
 }
 if(Test-Path -LiteralPath $pending){throw 'Interrupted operation detected. Run Recover.cmd before starting the game.'}
 if($Mode -eq 'Install'){
  $payload=(Resolve-Path -LiteralPath $PayloadPath).Path;Plain $payload
  $manifestPath=Join-Path $payload 'manifest.json';Plain $manifestPath
  $m=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json;Manifest $m
  $newDll=Join-Path $payload 'GameCyclingDLL_Master.dll';$newPak=Join-Path $payload $m.pak
  Plain $newDll;Plain $newPak
  if((Hash $newDll) -ne $m.dll_after -or (Hash $newPak) -ne $m.sha256){throw 'Payload hash mismatch; extract package again'}
  if((Current $dll) -eq $m.dll_after -and (Current $pak) -eq $m.sha256){
   if(!(Test-Path -LiteralPath $statePath) -or (Current $original) -ne $m.dll_before){throw 'Unmanaged old installation: restore with old installer first'}
   $state=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json;Manifest $state
   if($state.dll_before -ne $m.dll_before -or $state.dll_after -ne $m.dll_after -or $state.sha256 -ne $m.sha256){throw 'Installer state mismatch'}
   Write-Host 'Already installed; files and original backup verified.';exit
  }
  if((Current $dll) -ne $m.dll_before -or (Test-Path -LiteralPath $pak) -or (Test-Path -LiteralPath $statePath)){throw 'Unknown version or existing mod; restore previous installation first'}
 }else{
  if(!(Test-Path -LiteralPath $statePath)){throw 'Installer state missing; do not overwrite files manually'}
  $m=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json;Manifest $m
  if((Current $dll) -ne $m.dll_after -or (Current $pak) -ne $m.sha256 -or (Current $original) -ne $m.dll_before){throw 'Installed files or original backup changed; preserve files and consult recovery instructions'}
  if($Mode -eq 'Check'){Write-Host 'PASS: DLL, overlay and original backup verified.';exit}
 }
 $volume=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($game))
 $bytes=(Get-Item -LiteralPath $dll).Length
 if($Mode -eq 'Install'){$bytes+=(Get-Item -LiteralPath $newPak).Length+(Get-Item -LiteralPath $newDll).Length}
 else{$bytes+=(Get-Item -LiteralPath $pak).Length}
 if($volume.AvailableFreeSpace -lt (4*$bytes+64MB)){throw 'Insufficient free space for verified staging and rollback backups'}
 if(Test-Path -LiteralPath $original){if((Hash $original) -ne $m.dll_before){throw 'Original backup damaged; refusing replacement'}}
 else{AtomicCopy $dll $original $m.dll_before}
 $name='txn-'+[Guid]::NewGuid().ToString('N');$dir=Join-Path $backup $name
 [IO.Directory]::CreateDirectory($dir) | Out-Null
 $before=@{dll=(Current $dll);pak=(Current $pak);state=(Current $statePath)}
 AtomicCopy $dll (Join-Path $dir 'before.dll') $before.dll
 if($before.pak -ne 'absent'){AtomicCopy $pak (Join-Path $dir 'before.pak') $before.pak}
 if($before.state -ne 'absent'){AtomicCopy $statePath (Join-Path $dir 'before.json') $before.state}
 if($Mode -eq 'Install'){
  AtomicCopy $newDll (Join-Path $dir 'next.dll') $m.dll_after
  AtomicCopy $newPak (Join-Path $dir 'next.pak') $m.sha256
  AtomicJson $m (Join-Path $dir 'next.json')
  $after=@{dll=$m.dll_after;pak=$m.sha256;state=(Hash (Join-Path $dir 'next.json'))}
 }else{$after=@{dll=$m.dll_before;pak='absent';state='absent'}}
 $journal=@{schema=1;transaction=$name;game=$game;mode=$Mode;before=$before;after=$after}
 Closed
 if((Current $dll) -ne $before.dll -or (Current $pak) -ne $before.pak -or (Current $statePath) -ne $before.state){throw 'Files changed during preparation'}
 AtomicJson $journal $pending
 try {
  if($Mode -eq 'Install'){
   AtomicCopy (Join-Path $dir 'next.dll') $dll $after.dll
   AtomicCopy (Join-Path $dir 'next.pak') $pak $after.pak
   AtomicCopy (Join-Path $dir 'next.json') $statePath $after.state
  }else{
   AtomicCopy $original $dll $after.dll
   [IO.File]::Move($pak,(Join-Path $dir 'disabled-overlay.pak'))
   [IO.File]::Move($statePath,(Join-Path $dir 'uninstalled.json'))
  }
  if((Current $dll) -ne $after.dll -or (Current $pak) -ne $after.pak -or (Current $statePath) -ne $after.state){throw 'Final verification failed'}
  [IO.File]::Move($pending,(Join-Path $dir 'completed.json'))
 }catch{
  $failure=$_.Exception.Message
  try {Rollback} catch {throw ('Failed: '+$failure+'; recovery incomplete: '+$_.Exception.Message+'. Keep backups and run Recover.cmd after fixing the cause.')}
  throw ('Operation failed; previous state restored: '+$failure)
 }
 if($Mode -eq 'Install'){Write-Host 'Installed and verified. Choose Dansk (Danish). English remains original.'}
 else{Write-Host 'Uninstalled and verified. Original DLL restored; backups retained.'}
} finally {if($null -ne $lock){$lock.Dispose()}}
