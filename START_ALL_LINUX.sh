#!/bin/bash

# ============================================
# Start All Services - Linux/macOS Script
# ============================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo ""
echo "========================================"
echo "Google Drive Sync - Start All Services"
echo "========================================"
echo ""

# Check environment variable
if [ -z "$GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON" ]; then
    echo "WARNING: GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set!"
    echo ""
    echo "Set it with:"
    echo "  export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/your/service-account-key.json"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check Redis
echo "Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Redis is not running!"
    echo ""
    echo "Start Redis with:"
    echo "  redis-server"
    echo ""
    exit 1
fi
echo "✓ Redis is running"

# Check Node
echo ""
echo "Checking Node.js..."
if ! node --version > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Node.js not found!"
    echo ""
    echo "Install Node.js v16+: https://nodejs.org/"
    echo ""
    exit 1
fi
echo "✓ Node.js is installed"

# Check Python
echo ""
echo "Checking Python..."
if ! python --version > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Python not found!"
    echo ""
    echo "Install Python 3.9+: https://www.python.org/"
    echo ""
    exit 1
fi
echo "✓ Python is installed"

echo ""
echo "========================================"
echo "Starting services..."
echo "========================================"
echo ""

# Export environment for subprocesses
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON="$GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"

# Create log directory
mkdir -p "$SCRIPT_DIR/logs"

# Function to start service with tmux (or open new terminal)
start_service() {
    local name=$1
    local cmd=$2
    local dir=$3

    echo "[!] Starting $name..."

    if command -v tmux &> /dev/null; then
        # Use tmux if available
        tmux new-session -d -s "$name" -c "$dir" "$cmd"
        echo "✓ $name started in tmux session '$name'"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS: Use Terminal.app
        osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$dir' && $cmd"
end tell
EOF
        echo "✓ $name started in new Terminal window"
    else
        # Linux: Use gnome-terminal or xterm
        if command -v gnome-terminal &> /dev/null; then
            gnome-terminal -- bash -c "cd '$dir' && $cmd; exec bash"
        elif command -v xterm &> /dev/null; then
            xterm -e "cd '$dir' && $cmd; bash" &
        else
            # Fallback: run in background
            (cd "$dir" && $cmd > "$SCRIPT_DIR/logs/${name}.log" 2>&1) &
            echo "✓ $name started in background (logs: logs/${name}.log)"
        fi
    fi
}

# Start Celery Worker
start_service "Celery Worker" \
    "celery -A celery_app worker --loglevel=info" \
    "$BACKEND_DIR"

sleep 2

# Start FastAPI
start_service "FastAPI Backend" \
    "python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000" \
    "$BACKEND_DIR"

sleep 2

# Start Frontend
start_service "Next.js Frontend" \
    "npm run dev" \
    "$FRONTEND_DIR"

echo ""
echo "========================================"
echo "✓ All services started!"
echo "========================================"
echo ""
echo "Services running:"
echo "  Celery Worker:  Queue for background tasks"
echo "  FastAPI:        http://localhost:8000"
echo "  Next.js:        http://localhost:3000"
echo ""
echo "Next steps:"
echo "  1. Open your browser: http://localhost:3000"
echo "  2. Login with your credentials"
echo "  3. Navigate to 'Drive Sync' in sidebar"
echo "  4. Click 'Start Sync Now'"
echo ""

if command -v tmux &> /dev/null; then
    echo "Managing tmux sessions:"
    echo "  tmux list-sessions         # List all sessions"
    echo "  tmux attach -t 'Celery Worker'  # Attach to Celery"
    echo "  tmux attach -t 'FastAPI Backend'  # Attach to API"
    echo "  tmux attach -t 'Next.js Frontend'  # Attach to Frontend"
    echo "  tmux kill-session -t <name>  # Kill a session"
    echo ""
fi

echo "Logs location: logs/"
echo "Documentation: RUN_LIVE_SERVER.md"
echo ""

# Give user time to read
sleep 3

# Open browser if possible
if command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:3000" 2>/dev/null &
elif command -v open &> /dev/null; then
    open "http://localhost:3000" 2>/dev/null &
fi

echo "Opening browser... http://localhost:3000"
echo ""
