git init

# Commit 1
git add README.md .gitignore .env.example docker-compose.yml
git commit -m "Initial commit: Project structure and environment setup"

# Commit 2
git add backend/data/
git add scripts/generate_data.py
git commit -m "feat(data): build synthetic ledger and bank statement generator"

# Commit 3
git add backend/app/engine/matcher.py
git commit -m "feat(engine): implement exact ID and duplicate matching"

# Commit 4
git add backend/app/models.py backend/app/schemas.py backend/app/database.py
git commit -m "feat(db): configure postgres asyncpg models and schemas"

# Commit 5
git add backend/app/main.py backend/app/tasks.py backend/requirements.txt backend/Dockerfile
git commit -m "feat(api): setup fastapi structure and celery worker config"

# Commit 6
git add backend/app/api/
git commit -m "feat(api): implement breaks retrieval and resolution endpoints"

# Commit 7
git add scripts/evaluate_standalone.py scripts/test_integration.py scripts/test_upload_api.py scripts/smoke_test.py
git commit -m "chore(eval): add standalone evaluation scripts for precision metrics"

# Commit 8
git add frontend/package.json frontend/vite.config.js frontend/index.html frontend/src/main.jsx frontend/src/index.css frontend/Dockerfile
git commit -m "feat(ui): initialize vite react dashboard with breaks table"

# Commit 9
git add frontend/src/api.js
git commit -m "feat(ui): add API integration helpers"

# Commit 10
git add frontend/src/App.jsx
git commit -m "feat(ui): implement manual resolution and file upload support"

# Commit 11
git add technical_breakdown.md
git commit -m "docs: add comprehensive technical breakdown"

# Commit 12 (catch all)
git add .
git commit -m "feat(ai): integrate gemini llm for automated break resolution analysis"

# Push
git branch -M main
git remote add origin https://github.com/Wali05/ledger-recon.git
git push -u origin main
