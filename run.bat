@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Openstudio - Word Search & Crossword Book Studio
echo ===================================================
echo.

if not exist "frontend\dist\index.html" (
    echo Frontend build not found. Building Openstudio UI...
    cd frontend
    if not exist "node_modules" (
        call npm install
    )
    call npm run build
    cd ..
)

echo Starting Openstudio on http://localhost:8000 ...
cd backend
python -m uvicorn app.main:app --port 8000 --reload
