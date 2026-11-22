#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f "frontend/dist/index.html" ]; then
  echo "Frontend build not found. Building Openstudio UI..."
  cd frontend
  [ ! -d "node_modules" ] && npm install
  npm run build
  cd ..
fi

echo "Starting Openstudio on http://localhost:8000 ..."
cd backend
python -m uvicorn app.main:app --port 8000 --reload
