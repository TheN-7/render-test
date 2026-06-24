param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$previewRoot = Join-Path $Root 'gui\ship_previews'
$previewMediumRoot = Join-Path $previewRoot 'medium'
$silhouetteRoot = Join-Path $Root 'gui\ships_silhouettes'
$shipIconRoot = Join-Path $Root 'gui\ship_icons'

if (-not (Test-Path $previewRoot)) {
    throw "Preview directory not found: $previewRoot"
}

if (-not (Test-Path $silhouetteRoot)) {
    New-Item -ItemType Directory -Path $silhouetteRoot -Force | Out-Null
}

$silhouetteColor = [System.Drawing.Color]::FromArgb(255, 38, 29, 26)

$previewFiles = @{}
Get-ChildItem $previewRoot -File -Filter *.png | ForEach-Object {
    $previewFiles[$_.BaseName] = $_.FullName
}
if (Test-Path $previewMediumRoot) {
    Get-ChildItem $previewMediumRoot -File -Filter *.png | ForEach-Object {
        if (-not $previewFiles.ContainsKey($_.BaseName)) {
            $previewFiles[$_.BaseName] = $_.FullName
        }
    }
}

$generated = 0
$skippedCovered = 0
$skippedExisting = 0
$errors = 0

foreach ($code in ($previewFiles.Keys | Sort-Object)) {
    $silhouettePath = Join-Path $silhouetteRoot "$code.png"
    $iconPath = Join-Path $shipIconRoot "$code.png"

    if ((Test-Path $iconPath) -or ((Test-Path $silhouettePath) -and -not $Force)) {
        if (Test-Path $iconPath) {
            $skippedCovered++
        } else {
            $skippedExisting++
        }
        continue
    }

    $sourcePath = $previewFiles[$code]
    $source = $null
    $target = $null

    try {
        $source = [System.Drawing.Bitmap]::FromFile($sourcePath)
        $target = New-Object System.Drawing.Bitmap($source.Width, $source.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)

        for ($y = 0; $y -lt $source.Height; $y++) {
            for ($x = 0; $x -lt $source.Width; $x++) {
                $pixel = $source.GetPixel($x, $y)
                if ($pixel.A -le 0) {
                    $target.SetPixel($x, $y, [System.Drawing.Color]::FromArgb(0, 0, 0, 0))
                    continue
                }
                $target.SetPixel($x, $y, [System.Drawing.Color]::FromArgb($pixel.A, $silhouetteColor.R, $silhouetteColor.G, $silhouetteColor.B))
            }
        }

        $target.Save($silhouettePath, [System.Drawing.Imaging.ImageFormat]::Png)
        $generated++
    } catch {
        $errors++
        Write-Warning ("Failed to generate silhouette for {0}: {1}" -f $code, $_.Exception.Message)
    } finally {
        if ($source) { $source.Dispose() }
        if ($target) { $target.Dispose() }
    }
}

Write-Output ("Generated silhouettes: {0}" -f $generated)
Write-Output ("Skipped due to ship_icons coverage: {0}" -f $skippedCovered)
Write-Output ("Skipped due to existing silhouettes: {0}" -f $skippedExisting)
Write-Output ("Errors: {0}" -f $errors)
