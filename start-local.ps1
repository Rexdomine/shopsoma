# Shopsoma Local Development Server Launcher
$ErrorActionPreference = "Stop"

Write-Host "Starting Shopsoma Local Development Servers..." -ForegroundColor Cyan

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $rootDir "shopsoma-backend"
$frontendDir = Join-Path $rootDir "shopsoma-frontend"

$backendPython = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $backendPython)) {
    Write-Host "Error: Backend virtual environment not found at $backendPython" -ForegroundColor Red
    exit 1
}

Write-Host "1. Starting FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Green
$backendProcess = Start-Process -FilePath $backendPython -ArgumentList "-m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" -WorkingDirectory $backendDir -PassThru

Write-Host "2. Starting React Vite Frontend on http://localhost:5173..." -ForegroundColor Green
$frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory $frontendDir -PassThru

Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host " Shopsoma is running locally!" -ForegroundColor Green
Write-Host "   Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host "   Backend:  http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "   API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Yellow
Write-Host "   Admin:    admin@shopsoma.com / Admin123" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "Press Ctrl+C or close the window to stop.`n"

try {
    Wait-Process -Id $backendProcess.Id, $frontendProcess.Id
} finally {
    if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id -Force }
    if (-not $frontendProcess.HasExited) { Stop-Process -Id $frontendProcess.Id -Force }
}
