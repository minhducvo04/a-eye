$ErrorActionPreference = "Stop"
. C:\kyra-work\venv-bench\Scripts\Activate.ps1
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m uvicorn boxsvc.app:app --host 0.0.0.0 --port 8090
