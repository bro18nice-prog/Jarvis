# Instaleaza dependentele si modelele in folderul proiectului.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # descarcarile merg mult mai repede asa

$src  = Split-Path -Parent $PSScriptRoot
$root = $src

function Step($n, $msg) { Write-Host ""; Write-Host "[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "    OK  $msg" -ForegroundColor Green }
function Warn($msg)     { Write-Host "    !!  $msg" -ForegroundColor Yellow }

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   INSTALARE JARVIS  ->  $root" -ForegroundColor Cyan
Write-Host "   Python, modelele si cache-urile stau in proiect." -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

Step 1 "Pregatesc folderul $root"
New-Item -ItemType Directory -Force -Path $root | Out-Null
foreach ($d in "tools","tools\tmp","models","models\piper","models\hf","data","config") {
    New-Item -ItemType Directory -Force -Path (Join-Path $root $d) | Out-Null
}

# Pastreaza cache-urile descarcate in proiect.
$env:UV_PYTHON_INSTALL_DIR = "$root\tools\python"
$env:UV_CACHE_DIR          = "$root\tools\uv-cache"
$env:UV_LINK_MODE          = "copy"
$env:HF_HOME               = "$root\models\hf"
$env:TEMP                  = "$root\tools\tmp"
$env:TMP                   = "$root\tools\tmp"
Ok "Cache-urile si fisierele temporare merg in $root\tools"

Step 2 "Descarc uv (instalatorul de Python, un singur .exe)"
$uv = "$root\tools\uv.exe"
if (-not (Test-Path $uv)) {
    $zip = "$root\tools\tmp\uv.zip"
    Invoke-WebRequest "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath "$root\tools\tmp\uv" -Force
    Copy-Item "$root\tools\tmp\uv\uv.exe" $uv -Force
}
Ok "uv gata"

Step 3 "Instalez Python 3.11 privat pentru Jarvis (doar in $root\tools\python)"
if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    & $uv venv "$root\.venv" --python 3.11 --python-preference only-managed
    if ($LASTEXITCODE -ne 0) { throw "Nu am putut crea mediul Python." }
}
$py = "$root\.venv\Scripts\python.exe"
Ok "Python: $py"

Step 4 "Instalez bibliotecile de baza (cateva minute)"
& $uv pip install --python $py -r "$root\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Instalarea bibliotecilor de baza a esuat." }
Ok "Biblioteci de baza instalate"

Step 5 "Instalez extra (voce Piper, cautare). Daca una pica, Jarvis merge si fara ea"
foreach ($pkg in "piper-tts>=1.3.0", "pyttsx3", "ddgs") {
    & $uv pip install --python $py $pkg
    if ($LASTEXITCODE -eq 0) { Ok $pkg } else { Warn "$pkg nu s-a instalat (exista rezerva)" }
}

Step 6 "Placa video NVIDIA"
$gpu = $null
try { $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null) } catch {}
if ($gpu) {
    Ok "Am gasit: $gpu"
    Write-Host "    Instalez bibliotecile CUDA pentru Whisper (~1 GB, in proiect)..."
    & $uv pip install --python $py "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
    if ($LASTEXITCODE -eq 0) { Ok "CUDA gata" } else { Warn "CUDA nu s-a instalat, Whisper va merge pe procesor" }
} else {
    Warn "Nu gasesc placa NVIDIA (nvidia-smi). Whisper va merge pe procesor."
}

Step 7 "Descarc vocea romaneasca (Piper - Mihai)"
$voiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ro/ro_RO/mihai/medium/ro_RO-mihai-medium"
foreach ($ext in ".onnx", ".onnx.json") {
    $out = "$root\models\piper\ro_RO-mihai-medium$ext"
    if (-not (Test-Path $out)) { Invoke-WebRequest "$voiceBase$ext" -OutFile $out }
}
Ok "Vocea e in $root\models\piper"

Step 8 "Descarc modelul de recunoastere vocala Whisper (~1.5 GB prima data)"
& $py "$root\app\prefetch.py"
if ($LASTEXITCODE -eq 0) { Ok "Whisper gata" } else { Warn "Whisper se va descarca la prima pornire" }

Step 9 "Setari"
$cfg = "$root\config\setari.env"
if (-not (Test-Path $cfg)) { Copy-Item "$root\config\setari.exemplu.env" $cfg }
$hasKey = (Get-Content $cfg -Raw) -match "GEMINI_API_KEY=AI"
if ($hasKey) { Ok "Cheia Gemini e pusa" } else { Warn "Mai trebuie pusa cheia Gemini in $cfg (vezi CITESTE-MA.txt)" }

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "   GATA! Porneste-l cu $root\DESCHIDE-PANOU.bat" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
"instalat $(Get-Date -Format s)" | Out-File "$root\data\instalat.txt" -Encoding utf8