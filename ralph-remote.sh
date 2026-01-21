#!/usr/bin/env bash
set -euo pipefail

# ralph-remote.sh: Execute Ralph against a remote repository
#
# This script:
# 1. SSH to specified host
# 2. Clone the target repo to a working directory
# 3. Remove the remote to prevent accidental pushes
# 4. Copy up Ralph, outer prompt, and inner prompt
# 5. Run Ralph with the specified task

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
RALPH_SCRIPT="${SCRIPT_DIR}/ralph.py"
DEFAULT_OUTER_PROMPT="${SCRIPT_DIR}/prompts/outer-prompt-default.md"
SSH_PORT=22
WORKING_DIR="."
DRY_RUN=false
MAX_ITERATIONS=10
MAX_TURNS=50
MODEL="opus"
CLI_TYPE="claude"

usage() {
    cat <<EOF
Usage: $0 [OPTIONS] --host HOST --repo REPO_URL --inner-prompt PROMPT

Execute Ralph against a remote repository via SSH.

Required arguments:
  --host HOST              SSH host to connect to
  --repo REPO_URL         Git repository URL to clone

Prompt arguments (one required):
  --inner-prompt PROMPT   Inner prompt (task description) to pass to Ralph
  --inner-prompt-file FILE  Read inner prompt from file

SSH options:
  --port PORT             SSH port (default: 22)
  --key KEY_FILE          SSH private key file
  --user USER             SSH user

Remote execution options:
  --working-dir DIR       Working directory on remote host (default: .)
  --outer-prompt FILE     Outer prompt template file (default: prompts/outer-prompt-default.md)

Ralph options:
  --max-iterations N      Maximum Ralph iterations (default: 10)
  --max-turns N          Maximum turns per iteration (default: 50)
  --model MODEL          Claude model: opus|sonnet|haiku (default: opus)
  --cli-type TYPE        CLI type: claude|codex (default: claude)
  --dry-run              Show what would be executed without running

Examples:
  # Basic usage with inline prompt
  $0 --host dev.example.com --repo https://github.com/org/repo \\
     --inner-prompt "Fix all type errors"

  # Using SSH key and custom port
  $0 --host dev.example.com --port 2222 --key ~/.ssh/id_rsa \\
     --repo git@github.com:org/repo.git \\
     --inner-prompt-file task.md --max-iterations 20

  # Dry run to test configuration
  $0 --host dev.example.com --repo https://github.com/org/repo \\
     --inner-prompt "Test task" --dry-run
EOF
    exit 1
}

# Parse arguments
INNER_PROMPT=""
INNER_PROMPT_FILE=""
HOST=""
REPO_URL=""
SSH_KEY=""
SSH_USER=""
OUTER_PROMPT="$DEFAULT_OUTER_PROMPT"

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
        --dry-run)
            DRY_RUN=true
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

# Validate required arguments
if [[ -z "$HOST" ]]; then
    echo "Error: --host is required"
    usage
fi

if [[ -z "$REPO_URL" ]]; then
    echo "Error: --repo is required"
    usage
fi

if [[ -z "$INNER_PROMPT" && -z "$INNER_PROMPT_FILE" ]]; then
    echo "Error: Either --inner-prompt or --inner-prompt-file is required"
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

# Extract repo name for working directory
REPO_NAME=$(basename "$REPO_URL" .git)
REMOTE_WORK_DIR="${WORKING_DIR}/${REPO_NAME}"
REMOTE_RALPH_DIR="${REMOTE_WORK_DIR}/.ralph"

echo "=========================================="
echo "Ralph Remote Execution"
echo "=========================================="
echo "Host:             $HOST:$SSH_PORT"
echo "Repository:       $REPO_URL"
echo "Remote work dir:  $REMOTE_WORK_DIR"
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
    echo "2. Remote commands:"
    cat <<'REMOTE_SCRIPT'
    # Clone repository
    git clone REPO_URL REMOTE_WORK_DIR
    cd REMOTE_WORK_DIR

    # Remove remote to prevent accidental pushes
    git remote remove origin

    # Create Ralph directory
    mkdir -p .ralph/prompts

    # Copy files (would be done via scp/rsync)
    # - ralph.py -> .ralph/
    # - outer-prompt.md -> .ralph/prompts/
    # - inner-prompt.md -> .ralph/

    # Execute Ralph
    python3 .ralph/ralph.py \
        --prompt-file .ralph/inner-prompt.md \
        --outer-prompt .ralph/prompts/outer-prompt.md \
        --max-iterations MAX_ITERATIONS \
        --max-turns MAX_TURNS \
        --model MODEL \
        --cli-type CLI_TYPE
REMOTE_SCRIPT
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

# Create remote working directory and Ralph directory
$SSH_CMD "mkdir -p ${REMOTE_WORK_DIR}"

echo "Step 2: Cloning repository..."

# Clone repository on remote
$SSH_CMD "cd ${WORKING_DIR} && git clone ${REPO_URL} ${REPO_NAME} 2>&1" || {
    echo "Error: Failed to clone repository"
    exit 1
}

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

echo ""
echo "=========================================="
echo "Starting Ralph execution on remote host..."
echo "=========================================="
echo ""

# Execute Ralph on remote
$SSH_CMD "cd ${REMOTE_WORK_DIR} && python3 .ralph/ralph.py \
    --prompt-file .ralph/inner-prompt.md \
    --outer-prompt .ralph/prompts/outer-prompt.md \
    --max-iterations ${MAX_ITERATIONS} \
    --max-turns ${MAX_TURNS} \
    --model ${MODEL} \
    --cli-type ${CLI_TYPE}"

RALPH_EXIT_CODE=$?

echo ""
echo "=========================================="
echo "Ralph execution completed"
echo "Exit code: $RALPH_EXIT_CODE"
echo "=========================================="
echo ""
echo "Remote working directory: ${REMOTE_WORK_DIR}"
echo "To access results:"
echo "  $SSH_CMD"
echo "  cd ${REMOTE_WORK_DIR}"
echo ""

exit $RALPH_EXIT_CODE
