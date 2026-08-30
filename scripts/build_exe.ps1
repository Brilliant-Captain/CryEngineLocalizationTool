[CmdletBinding()]
param(
  [string]$OutputDir = (Join-Path $PSScriptRoot '..\release')
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$specs = @(
  (Join-Path $projectRoot 'packaging\CryEngineLocalization.spec'),
  (Join-Path $projectRoot 'packaging\CryEngineLocalizationCLI.spec')
)

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "Project Python not found: $python. Create .venv and install the project first."
}
& $python -c 'import PyInstaller' 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed. Run: python -m pip install pyinstaller"
}
& $python -c 'import fontTools' 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "fontTools is not installed. Run: python -m pip install -e '.[fonts]'"
}

$outputPath = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$workPath = Join-Path ([IO.Path]::GetTempPath()) ("cryengine_localization_pyinstaller_{0}" -f ([guid]::NewGuid().ToString('N')))
New-Item -ItemType Directory -Force -Path $workPath | Out-Null

try {
  foreach ($spec in $specs) {
    & $python -m PyInstaller $spec --clean --noconfirm --distpath $outputPath --workpath $workPath
    if ($LASTEXITCODE -ne 0) {
      throw "PyInstaller failed for $spec with exit code $LASTEXITCODE"
    }
  }

  $executables = @(
    (Join-Path $outputPath 'CryEngineLocalization.exe'),
    (Join-Path $outputPath 'cry-localize.exe')
  )
  foreach ($exe in $executables) {
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
      throw "Expected executable was not produced: $exe"
    }
  }

  $checksums = foreach ($exe in $executables) {
    $hash = Get-FileHash -LiteralPath $exe -Algorithm SHA256
    [pscustomobject]@{
      file = (Split-Path -Leaf $hash.Path)
      size = (Get-Item -LiteralPath $exe).Length
      sha256 = $hash.Hash
    }
    Write-Host "Built $exe"
    Write-Host "SHA256 $($hash.Hash)"
  }
  $checksums | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'SHA256SUMS.json') -Encoding UTF8
} finally {
  if (Test-Path -LiteralPath $workPath) {
    Remove-Item -LiteralPath $workPath -Recurse -Force -ErrorAction SilentlyContinue
  }
}
