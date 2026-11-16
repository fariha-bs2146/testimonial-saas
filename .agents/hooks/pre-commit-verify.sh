#!/usr/bin/env bash
# Pre-commit hook: runs pytest verification before allowing commits
set -e
echo "🔍 Running pre-commit agentic verification (pytest)..."
pytest -q
if [ $? -eq 0 ]; then
    echo "✅ All tests passed. Pre-commit check successful!"
else
    echo "❌ Tests failed. Commit aborted."
    exit 1
fi
