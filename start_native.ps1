# VoiceCraft Native Explanatory Engine Bootstrapper
# (Use this only if Docker fails completely to download massive PyTorch arrays)

Write-Host "Creating Native Python Environment..." -ForegroundColor Cyan
Set-Location Backend

if (!(Test-Path "venv")) {
    Write-Host "No venv detected. Bootstrapping new environment..."
    python -m venv venv
}

Write-Host "Activating Virtual Environment..." -ForegroundColor Cyan
.\venv\Scripts\activate

Write-Host "Installing Python Requirements natively (This downloads ~5GB of ML models)..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "Starting API Gateway natively without Celery overhead..." -ForegroundColor Green
uvicorn app.main:app --host 0.0.0.0 --port 8000
