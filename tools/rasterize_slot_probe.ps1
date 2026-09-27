param(
    [string]$OutDir = '',
    [string]$FontFamily = 'Microsoft YaHei UI',
    [ValidateRange(0.4,0.9)][double]$FontScale = 0.78,
    [ValidateSet('Regular','Bold')][string]$FontWeight = 'Regular'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$out = Join-Path (Split-Path $PSScriptRoot -Parent) 'work\slot-probe'
if ($OutDir) { $out = [IO.Path]::GetFullPath($OutDir) }
$plan = Get-Content -LiteralPath "$out\plan.json" -Encoding UTF8 -Raw | ConvertFrom-Json
$family = New-Object System.Drawing.FontFamily $FontFamily
$style = [System.Enum]::Parse([System.Drawing.FontStyle],$FontWeight)
if (-not $family.IsStyleAvailable($style)) { throw "Font style unavailable: $FontFamily $FontWeight" }
$config = [ordered]@{family=$family.Name;scale=$FontScale;weight=$FontWeight;rendering='AntiAliasGridFit'}
[IO.File]::WriteAllText("$out\font-config.json",($config | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
New-Item -ItemType Directory -Force "$out\glyphs" | Out-Null
foreach ($job in $plan.jobs) {
    $size = [int]$job.size
    $bmp = New-Object System.Drawing.Bitmap $size,$size,([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $font = New-Object System.Drawing.Font $family,([float]($size * $FontScale)),$style,([System.Drawing.GraphicsUnit]::Pixel)
    $fmt = [System.Drawing.StringFormat]::GenericTypographic.Clone()
    $fmt.Alignment = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::Transparent)
    $rect = New-Object System.Drawing.RectangleF 0,0,$size,$size
    $g.DrawString([string]$job.char,$font,[System.Drawing.Brushes]::White,$rect,$fmt)
    $lock = $bmp.LockBits((New-Object System.Drawing.Rectangle 0,0,$size,$size),[System.Drawing.Imaging.ImageLockMode]::ReadOnly,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $pixels = New-Object byte[] ($size * $size * 4)
    for ($y=0; $y -lt $size; $y++) {
        [Runtime.InteropServices.Marshal]::Copy([IntPtr]::Add($lock.Scan0,$y*$lock.Stride),$pixels,$y*$size*4,$size*4)
    }
    $bmp.UnlockBits($lock)
    [IO.File]::WriteAllBytes("$out\glyphs\$($job.key).bgra",$pixels)
    $bmp.Save("$out\glyphs\$($job.key).png",[System.Drawing.Imaging.ImageFormat]::Png)
    $fmt.Dispose(); $font.Dispose(); $g.Dispose(); $bmp.Dispose()
}
$family.Dispose()
Write-Host "Rasterized $($plan.jobs.Count) glyph variants."
