$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$ffmpeg = "C:\Users\home\.codex\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"
$reference = "C:\Users\home\AppData\Local\Temp\codex-clipboard-30f6f905-e974-4fd6-b5c0-c95852e35cb8.png"
$originals = Join-Path $PSScriptRoot "exact-originals-2048"
$posterCrops = Join-Path $PSScriptRoot "poster-cutouts-white-2048"

New-Item -ItemType Directory -Force -Path $originals, $posterCrops | Out-Null

$assets = @(
    @{ Source = "frontend\public\ratings\rating-4.png"; Name = "01-linguini-happy.png" },
    @{ Source = "frontend\public\ratings\rating-5.png"; Name = "02-linguini-love.png" },
    @{ Source = "frontend\public\linguini-logo-cool.png"; Name = "03-linguini-cool.png" },
    @{ Source = "frontend\public\badges\seek-and-find.webp"; Name = "04-farfalle-friend.png" },
    @{ Source = "frontend\public\badges\let-me-rephrase.webp"; Name = "05-macaroni-friend.png" },
    @{ Source = "frontend\public\badges\problem-solver.webp"; Name = "06-noodle-ball-friend.png" },
    @{ Source = "frontend\public\badges\count-me-in.webp"; Name = "07-rigatoni-family.png" },
    @{ Source = "frontend\public\badges\make-it-happen.webp"; Name = "08-ravioli-flag.png" },
    @{ Source = "frontend\public\badges\spot-and-say.webp"; Name = "09-rigatoni-magnifier.png" }
)

foreach ($asset in $assets) {
    $source = Join-Path $repoRoot $asset.Source
    $destination = Join-Path $originals $asset.Name
    & $ffmpeg -hide_banner -loglevel error -y -i $source -vf "scale=2048:2048:flags=lanczos" $destination
}

$wordmarkSource = Join-Path $repoRoot "frontend\public\linguini-wordmark.png"
& $ffmpeg -hide_banner -loglevel error -y -i $wordmarkSource -vf "scale=2400:800:flags=lanczos" (Join-Path $originals "00-linguini-wordmark.png")

$crops = @(
    @{ X = 9; Y = 210; Name = "01-linguini-happy.png" },
    @{ X = 170; Y = 210; Name = "02-linguini-love.png" },
    @{ X = 328; Y = 210; Name = "03-linguini-cool.png" },
    @{ X = 9; Y = 383; Name = "04-farfalle-friend.png" },
    @{ X = 170; Y = 383; Name = "05-macaroni-friend.png" },
    @{ X = 328; Y = 383; Name = "06-noodle-ball-friend.png" },
    @{ X = 9; Y = 544; Name = "07-rigatoni-family.png" },
    @{ X = 170; Y = 544; Name = "08-ravioli-flag.png" },
    @{ X = 328; Y = 544; Name = "09-rigatoni-magnifier.png" }
)

foreach ($crop in $crops) {
    $destination = Join-Path $posterCrops $crop.Name
    $filter = "crop=151:151:$($crop.X):$($crop.Y),scale=2048:2048:flags=lanczos"
    & $ffmpeg -hide_banner -loglevel error -y -i $reference -vf $filter $destination
}

Write-Host "Created exact originals in $originals"
Write-Host "Created poster-matching crops in $posterCrops"
