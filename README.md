# Openstudio

Unified vector-first **Word Search** and **Crossword** book publishing studio for KDP and print-ready interiors.

## Studios Included
- **Word Search Studio**: Chapter-based word-search puzzle books with customizable grids, directions, difficulty presets, clues, answer keys (1/2/4/6 per page), live SVG preview, and single vector PDF export (`/api/wordsearch/*`).
- **Crossword Book Studio**: Interconnected crossword puzzle books with deterministic grid construction, WordNet & AI clue authoring, quality checks, local SQLite/Alembic Project Library (autosave, duplicate, JSON backup/restore), live SVG preview, and verified vector PDF export (`/api/projects`, `/api/clues`, `/api/puzzles`, `/api/export`, etc.).

## Quickstart

### 1. Install dependencies
```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build
```

### 2. Run Openstudio (single server on port 8000)
- **Windows**: double-click `run.bat` or run `.\run.bat`
- **macOS / Linux**: `./run.sh`
- Open `http://localhost:8000`

### 3. Development mode (hot reload)
```bash
# Terminal 1 — Backend
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

### 4. Tests
```bash
# Backend (unified + Word Search + Crossword)
cd backend && python -m pytest -q

# Frontend (Openstudio + Word Search + Crossword)
cd frontend && npm test
```
