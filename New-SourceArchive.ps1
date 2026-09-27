param([string]$OutputPath=(Join-Path $PSScriptRoot 'build\releases\pcm2026-zh-source.zip'))
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root=$PSScriptRoot
$files=@(Get-ChildItem -LiteralPath $root -File | Where-Object {$_.Extension -in @('.md','.ps1','.cmd','.txt','.json') -or $_.Name -in @('LICENSE','.gitignore')})
foreach($dir in @('tools','translations','docs','tests','.github')){
    $files+=Get-ChildItem -LiteralPath (Join-Path $root $dir) -File -Recurse | Where-Object {$_.FullName -notmatch '[\\/]__pycache__[\\/]'}
}
if($files | Where-Object {$_.Extension -in @('.dll','.pdb','.pak','.cdb','.uasset','.uexp','.bgra','.zip','.pyc')}){throw 'Game resource or generated binary in source inventory'}
$target=[IO.Path]::GetFullPath($OutputPath)
if(Test-Path -LiteralPath $target){throw 'Source archive already exists'}
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
$stream=[IO.File]::Open($target,[IO.FileMode]::CreateNew)
$archive=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create)
try {
    foreach($file in $files){
        $relative=$file.FullName.Substring($root.Length+1).Replace('\','/')
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$file.FullName,('pcm2026-zh/'+$relative),[IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally {$archive.Dispose();$stream.Dispose()}
Write-Host ('Source ZIP: '+$target)
