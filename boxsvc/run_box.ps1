$ErrorActionPreference = "Stop"
# Local model copies on the GPU box, so nothing is downloaded at start.
$env:STT_MODEL = "C:\kyra-work\models\faster-whisper-large-v3-turbo"
$env:YOLO_WEIGHTS = "C:\kyra-work\models\YOLO11\yolo11n.pt"
$env:KOKORO_DIR = "C:\kyra-work\models\Kokoro-82M"
$env:HF_HUB_OFFLINE = "1"
. C:\kyra-work\venv-bench\Scripts\Activate.ps1
Set-Location (Split-Path $PSScriptRoot -Parent)
# Tailnet address only, not every interface.
python -m uvicorn boxsvc.app:app --host 100.93.176.7 --port 8090
