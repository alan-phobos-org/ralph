#!/usr/bin/env bash
set -euo pipefail

# ralph-remote.sh: Execute Ralph against a remote repository in tmux
#
# This script supports two modes:
# 1. Start mode: Clone repo, setup Ralph, start in tmux, detach
# 2. Resume mode: Reattach to existing tmux session

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env file
load_env_file() {
    local env_file="$1"

    if [[ ! -f "$env_file" ]]; then
        return 0
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments and blank lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue

        # Handle both "KEY=value" and "export KEY=value"
        if [[ "$line" =~ ^export[[:space:]]+([A-Z_][A-Z0-9_]*)=(.*)$ ]] || \
           [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"

            # Remove surrounding quotes
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"

            export "$key=$value"
        fi
    done < "$env_file"
}

# Expand tilde in paths
expand_tilde() {
    local path="$1"
    if [[ "$path" =~ ^\~ ]] && [[ -n "${HOME:-}" ]]; then
        echo "${path/#\~/$HOME}"
    else
        echo "$path"
    fi
}

# Load .env file (script dir first, then current dir)
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    load_env_file "${SCRIPT_DIR}/.env"
elif [[ -f "$(pwd)/.env" ]]; then
    load_env_file "$(pwd)/.env"
fi

# Default values with environment variable fallbacks
RALPH_SCRIPT="${SCRIPT_DIR}/ralph.py"
DEFAULT_OUTER_PROMPT="${SCRIPT_DIR}/prompts/outer-prompt-default.md"
SSH_PORT="${RALPH_REMOTE_PORT:-22}"
WORKING_DIR="${RALPH_REMOTE_WORKING_DIR:-.}"
DRY_RUN=false
MAX_ITERATIONS="${RALPH_REMOTE_MAX_ITERATIONS:-10}"
MAX_TURNS="${RALPH_REMOTE_MAX_TURNS:-50}"
MODEL="${RALPH_REMOTE_MODEL:-opus}"
CLI_TYPE="${RALPH_REMOTE_CLI_TYPE:-claude}"
RESUME_MODE=false
SESSION_NAME=""

usage() {
    cat <<EOF
Usage: $0 [OPTIONS] --host HOST [--resume SESSION | --repo REPO_URL --inner-prompt PROMPT]

Execute Ralph against a remote repository via SSH in a detached tmux session.

Modes:
  Start mode:  Start new Ralph session in tmux (requires --repo and prompt)
  Resume mode: Reattach to existing Ralph session (requires --resume)

Required arguments:
  --host HOST              SSH host to connect to

Start mode arguments:
  --repo REPO_URL         Git repository URL to clone
  --inner-prompt PROMPT   Inner prompt (task description) to pass to Ralph
  --inner-prompt-file FILE  Read inner prompt from file

Resume mode arguments:
  --resume SESSION        Reattach to existing tmux session
  --list                  List all Ralph sessions on remote host

SSH options:
  --port PORT             SSH port (default: 22)
  --key KEY_FILE          SSH private key file
  --user USER             SSH user

Remote execution options:
  --working-dir DIR       Working directory on remote host (default: .)
  --outer-prompt FILE     Outer prompt template file (default: prompts/outer-prompt-default.md)
  --session-name NAME     Custom tmux session name (default: ralph-REPO_NAME-TIMESTAMP)

Ralph options:
  --max-iterations N      Maximum Ralph iterations (default: 10)
  --max-turns N          Maximum turns per iteration (default: 50)
  --model MODEL          Claude model: opus|sonnet|haiku (default: opus)
  --cli-type TYPE        CLI type: claude|codex (default: claude)
  --dry-run              Show what would be executed without running
  --show-config          Display effective configuration and exit

Environment Variables:
  Configuration options can be set via environment variables or loaded from
  a .env file in the script directory or current directory. CLI arguments
  override environment variables.

  RALPH_REMOTE_HOST              SSH host to connect to
  RALPH_REMOTE_PORT              SSH port (default: 22)
  RALPH_REMOTE_KEY               SSH private key file (supports ~/)
  RALPH_REMOTE_USER              SSH user
  RALPH_REMOTE_REPO              Git repository URL
  RALPH_REMOTE_WORKING_DIR       Working directory (default: .)
  RALPH_REMOTE_MAX_ITERATIONS    Maximum iterations (default: 10)
  RALPH_REMOTE_MAX_TURNS         Maximum turns (default: 50)
  RALPH_REMOTE_MODEL             Claude model (default: opus)
  RALPH_REMOTE_CLI_TYPE          CLI type (default: claude)
  RALPH_REMOTE_OUTER_PROMPT      Outer prompt template (supports ~/)

  Example .env file:
    RALPH_REMOTE_HOST=135.181.155.74
    RALPH_REMOTE_PORT=28244
    RALPH_REMOTE_KEY=~/.ssh/id_rsa
    RALPH_REMOTE_REPO=https://github.com/org/repo

  Configuration priority (highest wins):
    1. CLI arguments
    2. Shell environment variables
    3. .env file
    4. Script defaults

Examples:
  # Start new Ralph session (detaches after setup)
  $0 --host dev.example.com --repo https://github.com/org/repo \\
     --inner-prompt "Fix all type errors"

  # List existing Ralph sessions on remote
  $0 --host dev.example.com --list

  # Resume existing Ralph session
  $0 --host dev.example.com --resume ralph-myrepo-20260121-183045

  # Start with custom session name
  $0 --host dev.example.com --repo https://github.com/org/repo \\
     --inner-prompt "Fix bugs" --session-name my-ralph-session

  # Dry run to test configuration
  $0 --host dev.example.com --repo https://github.com/org/repo \\
     --inner-prompt "Test task" --dry-run
EOF
    exit 1
}

# Parse arguments - initialize from environment variables
INNER_PROMPT=""
INNER_PROMPT_FILE=""
HOST="${RALPH_REMOTE_HOST:-}"
REPO_URL="${RALPH_REMOTE_REPO:-}"
SSH_KEY="$(expand_tilde "${RALPH_REMOTE_KEY:-}")"
SSH_USER="${RALPH_REMOTE_USER:-}"
OUTER_PROMPT="$(expand_tilde "${RALPH_REMOTE_OUTER_PROMPT:-$DEFAULT_OUTER_PROMPT}")"
LIST_SESSIONS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            SSH_PORT="$2"
            shift 2
            ;;
        --key)
            SSH_KEY="$2"
            shift 2
            ;;
        --user)
            SSH_USER="$2"
            shift 2
            ;;
        --repo)
            REPO_URL="$2"
            shift 2
            ;;
        --inner-prompt)
            INNER_PROMPT="$2"
            shift 2
            ;;
        --inner-prompt-file)
            INNER_PROMPT_FILE="$2"
            shift 2
            ;;
        --working-dir)
            WORKING_DIR="$2"
            shift 2
            ;;
        --outer-prompt)
            OUTER_PROMPT="$2"
            shift 2
            ;;
        --session-name)
            SESSION_NAME="$2"
            shift 2
            ;;
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --max-turns)
            MAX_TURNS="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --cli-type)
            CLI_TYPE="$2"
            shift 2
            ;;
        --resume)
            RESUME_MODE=true
            SESSION_NAME="$2"
            shift 2
            ;;
        --list)
            LIST_SESSIONS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --show-config)
            SHOW_CONFIG=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Error: Unknown option $1"
            usage
            ;;
    esac
done

# Show effective configuration if requested
if [[ "${SHOW_CONFIG:-false}" == "true" ]]; then
    echo "Effective Configuration:"
    echo "======================="
    echo "HOST:             ${HOST:-<not set>}"
    echo "SSH_PORT:         $SSH_PORT"
    echo "SSH_KEY:          ${SSH_KEY:-<not set>}"
    echo "SSH_USER:         ${SSH_USER:-<not set>}"
    echo "REPO_URL:         ${REPO_URL:-<not set>}"
    echo "WORKING_DIR:      $WORKING_DIR"
    echo "MAX_ITERATIONS:   $MAX_ITERATIONS"
    echo "MAX_TURNS:        $MAX_TURNS"
    echo "MODEL:            $MODEL"
    echo "CLI_TYPE:         $CLI_TYPE"
    echo "OUTER_PROMPT:     $OUTER_PROMPT"
    exit 0
fi

# Validate required arguments
if [[ -z "$HOST" ]]; then
    echo "Error: --host is required (or set RALPH_REMOTE_HOST in .env file)" >&2
    usage
fi

# Build SSH command
SSH_CMD="ssh -p $SSH_PORT"
if [[ -n "$SSH_KEY" ]]; then
    SSH_CMD="$SSH_CMD -i $SSH_KEY"
fi
if [[ -n "$SSH_USER" ]]; then
    SSH_CMD="$SSH_CMD ${SSH_USER}@${HOST}"
else
    SSH_CMD="$SSH_CMD $HOST"
fi

# Handle list mode
if [[ "$LIST_SESSIONS" == "true" ]]; then
    echo "Ralph sessions on $HOST:"
    echo "=========================================="
    $SSH_CMD "tmux list-sessions 2>/dev/null | grep '^ralph-' || echo 'No Ralph sessions found'"
    exit 0
fi

# Handle resume mode
if [[ "$RESUME_MODE" == "true" ]]; then
    if [[ -z "$SESSION_NAME" ]]; then
        echo "Error: --resume requires a session name"
        echo ""
        echo "List available sessions with: $0 --host $HOST --list"
        exit 1
    fi

    echo "=========================================="
    echo "Resuming Ralph Remote Session"
    echo "=========================================="
    echo "Host:    $HOST:$SSH_PORT"
    echo "Session: $SESSION_NAME"
    echo "=========================================="
    echo ""
    echo "Attaching to tmux session (press Ctrl+b d to detach)..."
    echo ""

    exec $SSH_CMD -t "tmux attach-session -t ${SESSION_NAME}"
fi

# Start mode validation
if [[ -z "$REPO_URL" ]]; then
    echo "Error: --repo is required for start mode (or set RALPH_REMOTE_REPO in .env file)" >&2
    echo "Use --resume SESSION to reattach to existing session"
    usage
fi

if [[ -z "$INNER_PROMPT" && -z "$INNER_PROMPT_FILE" ]]; then
    echo "Error: Either --inner-prompt or --inner-prompt-file is required for start mode"
    usage
fi

# Handle inner prompt from file
if [[ -n "$INNER_PROMPT_FILE" ]]; then
    if [[ ! -f "$INNER_PROMPT_FILE" ]]; then
        echo "Error: Inner prompt file not found: $INNER_PROMPT_FILE"
        exit 1
    fi
    INNER_PROMPT=$(cat "$INNER_PROMPT_FILE")
fi

# Validate files exist
if [[ ! -f "$RALPH_SCRIPT" ]]; then
    echo "Error: Ralph script not found: $RALPH_SCRIPT"
    exit 1
fi

if [[ ! -f "$OUTER_PROMPT" ]]; then
    echo "Error: Outer prompt file not found: $OUTER_PROMPT"
    exit 1
fi

# Extract repo name and create session name
REPO_NAME=$(basename "$REPO_URL" .git)
if [[ -z "$SESSION_NAME" ]]; then
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    SESSION_NAME="ralph-${REPO_NAME}-${TIMESTAMP}"
fi

REMOTE_WORK_DIR="${WORKING_DIR}/${REPO_NAME}"
REMOTE_RALPH_DIR="${REMOTE_WORK_DIR}/.ralph"

echo "=========================================="
echo "Ralph Remote Execution (Start Mode)"
echo "=========================================="
echo "Host:             $HOST:$SSH_PORT"
echo "Repository:       $REPO_URL"
echo "Remote work dir:  $REMOTE_WORK_DIR"
echo "Session name:     $SESSION_NAME"
echo "Inner prompt:     ${INNER_PROMPT:0:50}..."
echo "Outer prompt:     $OUTER_PROMPT"
echo "Max iterations:   $MAX_ITERATIONS"
echo "Model:            $MODEL"
echo "CLI type:         $CLI_TYPE"
echo "Dry run:          $DRY_RUN"
echo "=========================================="

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "DRY RUN - Would execute the following:"
    echo ""
    echo "1. SSH command: $SSH_CMD"
    echo ""
    echo "2. Remote setup commands:"
    cat <<REMOTE_SCRIPT
    # Clone repository
    git clone ${REPO_URL} ${REMOTE_WORK_DIR}
    cd ${REMOTE_WORK_DIR}
    git remote remove origin

    # Create Ralph directory and copy files
    mkdir -p .ralph/prompts
    # (ralph.py, prompts, inner-prompt.md copied via scp)

    # Create tmux session
    tmux new-session -d -s ${SESSION_NAME} -c ${REMOTE_WORK_DIR}

    # Start Ralph in tmux session
    tmux send-keys -t ${SESSION_NAME} "python3 .ralph/ralph.py \\
        --prompt-file .ralph/inner-prompt.md \\
        --outer-prompt .ralph/prompts/outer-prompt.md \\
        --max-iterations ${MAX_ITERATIONS} \\
        --max-turns ${MAX_TURNS} \\
        --model ${MODEL} \\
        --cli-type ${CLI_TYPE} 2>&1 | tee .ralph/ralph.log" C-m
REMOTE_SCRIPT
    echo ""
    echo "3. Resume with:"
    echo "   $0 --host $HOST --resume ${SESSION_NAME}"
    echo ""
    echo "DRY RUN complete. Use without --dry-run to execute."
    exit 0
fi

# Create temporary directory for files to transfer
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Prepare files
cp "$RALPH_SCRIPT" "$TEMP_DIR/ralph.py"
cp "$OUTER_PROMPT" "$TEMP_DIR/outer-prompt.md"
echo "$INNER_PROMPT" > "$TEMP_DIR/inner-prompt.md"

echo ""
echo "Step 1: Setting up remote environment..."

# Create remote working directory
$SSH_CMD "mkdir -p ${REMOTE_WORK_DIR}" 2>/dev/null || true

echo "Step 2: Cloning repository..."

# Clone repository on remote (skip if already exists)
if $SSH_CMD "test -d ${REMOTE_WORK_DIR}/.git"; then
    echo "Repository already exists at ${REMOTE_WORK_DIR}, skipping clone..."
else
    $SSH_CMD "cd ${WORKING_DIR} && git clone ${REPO_URL} ${REPO_NAME}" || {
        echo "Error: Failed to clone repository"
        exit 1
    }
fi

echo "Step 3: Removing git remote..."

# Remove remote to prevent accidental pushes
$SSH_CMD "cd ${REMOTE_WORK_DIR} && git remote remove origin 2>&1" || {
    echo "Warning: Failed to remove remote (may not exist)"
}

echo "Step 4: Creating Ralph directory..."

# Create Ralph directory structure
$SSH_CMD "mkdir -p ${REMOTE_RALPH_DIR}/prompts"

echo "Step 5: Copying Ralph files..."

# Transfer files using scp
SCP_CMD="scp -P $SSH_PORT"
if [[ -n "$SSH_KEY" ]]; then
    SCP_CMD="$SCP_CMD -i $SSH_KEY"
fi

SCP_TARGET="${SSH_USER:+${SSH_USER}@}${HOST}"

$SCP_CMD "$TEMP_DIR/ralph.py" "${SCP_TARGET}:${REMOTE_RALPH_DIR}/" || {
    echo "Error: Failed to copy ralph.py"
    exit 1
}

$SCP_CMD "$TEMP_DIR/outer-prompt.md" "${SCP_TARGET}:${REMOTE_RALPH_DIR}/prompts/" || {
    echo "Error: Failed to copy outer prompt"
    exit 1
}

$SCP_CMD "$TEMP_DIR/inner-prompt.md" "${SCP_TARGET}:${REMOTE_RALPH_DIR}/" || {
    echo "Error: Failed to copy inner prompt"
    exit 1
}

echo "Step 6: Making ralph.py executable..."
$SSH_CMD "chmod +x ${REMOTE_RALPH_DIR}/ralph.py"

echo "Step 7: Creating tmux session..."

# Check if session already exists
if $SSH_CMD "tmux has-session -t ${SESSION_NAME} 2>/dev/null"; then
    echo "Error: tmux session '${SESSION_NAME}' already exists"
    echo "Use --resume ${SESSION_NAME} to attach, or choose a different --session-name"
    exit 1
fi

# Create detached tmux session
$SSH_CMD "tmux new-session -d -s ${SESSION_NAME} -c ${REMOTE_WORK_DIR}"

echo "Step 8: Starting Ralph in tmux session..."

# Start Ralph in the tmux session with logging
$SSH_CMD "tmux send-keys -t ${SESSION_NAME} 'python3 .ralph/ralph.py \
    --prompt-file .ralph/inner-prompt.md \
    --outer-prompt .ralph/prompts/outer-prompt.md \
    --max-iterations ${MAX_ITERATIONS} \
    --max-turns ${MAX_TURNS} \
    --model ${MODEL} \
    --cli-type ${CLI_TYPE} 2>&1 | tee .ralph/ralph.log' C-m"

echo ""
echo "=========================================="
echo "Ralph session started successfully"
echo "=========================================="
echo ""
echo "Session name:    $SESSION_NAME"
echo "Working dir:     $REMOTE_WORK_DIR"
echo "Log file:        $REMOTE_WORK_DIR/.ralph/ralph.log"
echo ""
echo "To attach to the session:"
echo "  $0 --host $HOST --resume $SESSION_NAME"
echo ""
echo "To detach once attached:"
echo "  Press: Ctrl+b d"
echo ""
echo "To list all sessions:"
echo "  $0 --host $HOST --list"
echo ""
echo "To view logs without attaching:"
echo "  $SSH_CMD 'tail -f ${REMOTE_WORK_DIR}/.ralph/ralph.log'"
echo ""
echo "To kill the session:"
echo "  $SSH_CMD 'tmux kill-session -t $SESSION_NAME'"
echo ""
