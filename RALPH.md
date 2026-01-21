# Ralph Loop: Distilled Essentials

## Quick Start

```bash
# Local execution
./ralph.py "Fix all type errors" --max-iterations 15

# Remote execution (SSH + repo clone)
./ralph-remote.sh --host dev.example.com \
  --repo https://github.com/org/repo \
  --inner-prompt "Fix all linting errors" \
  --max-iterations 20

# Test remote configuration
./ralph-remote.sh --host dev.example.com \
  --repo https://github.com/org/repo \
  --inner-prompt "Test task" \
  --dry-run
```

## Core Design Principles

**Naive persistence beats sophisticated complexity.**

Ralph Loop feeds the same prompt repeatedly to an AI agent until task complete. Progress persists in files and git, not context.

### Why It Works

1. **External verification beats self-assessment** - Agent reviews its own work each iteration, identifies gaps, improves incrementally
2. **Self-correcting feedback** - Each iteration sees previous changes via git/files, fixes bugs, completes missing work
3. **Fresh context prevents rot** - When context fills, agent exits and fresh agent continues from file state
4. **File system is ground truth** - Git history + files persist across iterations; LLM memory does not

### Key Insight

Don't aim for perfect on first try. Let the loop refine through iteration. Trust the agent's ability to self-correct when it sees its own work.

## CLI Commands

### Claude Code (YOLO Mode)

```bash
# Environment
export CLAUDE_CODE_YOLO=1

# Command structure
claude --print \
  --dangerously-skip-permissions \
  --max-turns 50 \
  -p "your prompt here"

# Quick mode (haiku)
claude --print \
  --dangerously-skip-permissions \
  --max-turns 50 \
  --model haiku \
  -p "your prompt here"
```

### Codex CLI (YOLO Mode)

```bash
# Environment
export CLAUDE_CODE_YOLO=1

# Command structure
codex exec \
  -s danger-full-access \
  "your prompt here"

# Quick mode (low reasoning effort)
codex exec \
  -s danger-full-access \
  -c model_reasoning_effort=low \
  "your prompt here"
```

## Wrapper Prompt Lessons

Critical insights from crafting the ralph.py prompt wrapper:

### 1. ONE Task Per Invocation (STRICT)

**Problem:** Agent does multiple tasks, creates multiple commits, context fills too fast.

**Solution:** Enforce strict rule - do ONE thing, commit, STOP. Let loop re-run for next task.

```
TodoWrite (mark one in_progress) → Do ONE task → Update progress.md → Commit both → STOP
```

**CRITICAL:** After completing each task, STOP and update progress.md before continuing.
Do NOT batch multiple tasks in one iteration. This is MANDATORY, not optional.

### 2. Quality Gates Before Commit

**Problem:** Agent commits broken code, subsequent iterations waste time debugging.

**Solution:** Mandatory checks before commit:
- Tests pass
- Type checks pass
- Linters pass

### 3. Progress Tracking File (MANDATORY)

**Problem:** Agent forgets what's done, repeats work or misses tasks.

**Solution:** Maintain progress.md with:
- Timestamp
- What was accomplished
- What remains

**CRITICAL:** Progress updates are BLOCKING, not optional. No commit without progress.md update.

### 4. Review Previous Work

**Problem:** Fresh agent doesn't understand context.

**Solution:** Always start with:
```
- Check if progress.md exists, read it
- Review git log and git status
- Build on what exists
```

### 5. Explicit Completion Signal

**Problem:** Hard to detect when task truly complete.

**Solution:** Agent emits exact signal when done:
```
🎯 RALPH_LOOP_COMPLETE 🎯
```

### 6. Stop Immediately After Commit

**Problem:** Agent continues working after commit, making untracked changes.

**Solution:** Explicit instruction:
```
CRITICAL: STOP IMMEDIATELY after committing.
Do NOT continue with more work.
The loop will run you again for the next step.
```

**Reality Check:** This doesn't work reliably. See "Forcing Exits" section below.

### 7. TodoWrite for Task Tracking (MANDATORY)

**Problem:** Agent batches multiple tasks in one iteration, unclear what's in progress.

**Solution:** Use TodoWrite tool throughout:
- Create task list at start of iteration
- Mark ONE task as in_progress before working
- Mark completed immediately after finishing
- Never work on multiple tasks concurrently

**Enforcement:** Make TodoWrite usage mandatory in prompt, not optional.

## The Core Challenge: Forcing Exits

### The Problem

**LLMs are trained to be helpful and complete tasks.** Polite instructions like "STOP after committing" are routinely ignored. With `--max-turns 50`, an agent will happily complete multiple tasks, make multiple commits, and consume the entire context window in a single invocation.

This is a **widely reported issue** in the Ralph Loop community (Dec 2025 - Jan 2026). The agent's self-assessment mechanism is unreliable - it exits when it *thinks* it's complete, not when objectively complete.

### The Solution: Don't Trust Voluntary Compliance

**Force mechanical constraints** instead of relying on prompt instructions:

#### 1. Lower Max Turns Drastically

```python
"--max-turns", "8",  # Not 50! Forces smaller work units
```

If the agent needs more turns, it will exit and restart. This creates natural breakpoints.

#### 2. Detect Commits and Force Continuation

```python
def check_for_commit(result: IterationResult) -> bool:
    """Check if a commit was made during this iteration"""
    # Check output for commit confirmation
    if 'git commit' in result.output.lower():
        return True

    # Verify with git log (commits in last 30 seconds)
    try:
        log_result = subprocess.run(
            ['git', 'log', '-1', '--pretty=%H', '--since=30 seconds ago'],
            capture_output=True,
            text=True,
            timeout=3
        )
        return bool(log_result.stdout.strip())
    except:
        return False

# In main loop after each iteration:
if check_for_commit(result):
    print("✅ Commit detected - forcing exit to prevent overwork")
    continue  # Move to next iteration immediately
```

#### 3. Aggressive Timeouts

```python
timeout=180  # 3 minutes, not 10
```

Short timeouts prevent sprawling work sessions.

#### 4. More Confrontational Prompts

```python
wrapper = f"""CRITICAL INSTRUCTION - READ FIRST:
You are in iteration {iteration_num} of a Ralph Loop. You MUST:
1. Read progress.md FIRST (create if missing)
2. Do EXACTLY ONE task from what remains
3. Commit when that ONE task is done
4. Your process WILL BE TERMINATED after the commit

DO NOT try to complete multiple tasks. DO NOT continue after committing.
The loop will restart you for the next task.
```

#### 5. Stop Hooks (Advanced)

Anthropic's official Ralph Wiggum plugin (Dec 2025) uses **Stop Hooks** that intercept exit attempts and check completion criteria programmatically before allowing the agent to exit.

### Key Insight

**Mechanical constraints beat prompt instructions.** The agent wants to help by finishing everything - you must physically prevent it.

## Prompt Structure Template

```
CONTEXT:
- Check if progress.md exists and read it FIRST
- Review git log and git status
- Build incrementally on what exists

YOUR TASK:
[User's task description]

MANDATORY WORKFLOW - ONE TASK AT A TIME:
1. Use TodoWrite to create/update task list with remaining work
2. Mark ONE task as in_progress
3. Do ONLY that ONE task (do not batch multiple tasks)
4. Run all quality gates: tests, type checks, linters (all must pass)
5. Mark the task as completed in TodoWrite
6. Update progress.md with timestamp and summary (MANDATORY - not optional)
7. Commit work AND progress.md together
8. STOP IMMEDIATELY - do not continue to next task

CRITICAL: After completing each task, you MUST STOP and update progress.md before continuing.
Do NOT batch multiple tasks. The loop will re-run you for the next task.

COMPLETION SIGNAL:
When task FULLY complete (all requirements met, all tests passing), emit:

🎯 RALPH_LOOP_COMPLETE 🎯

Only emit when absolutely certain task is done.

Begin working on NEXT SINGLE task now. Remember: ONE task → Update progress.md → Commit → STOP
```

## Customizing the Outer Prompt

Ralph's outer prompt (the wrapper instructions) is now externalized and customizable.

### Default Outer Prompt

The default outer prompt is at `prompts/outer-prompt-default.md`. It contains the two-phase workflow:
- Phase 1: Planning (iterative refinement until detailed enough)
- Phase 2: Implementation (one task at a time)

### Custom Outer Prompt

Create your own outer prompt template for specialized workflows:

```bash
# Create custom outer prompt
cat > prompts/outer-prompt-aggressive.md <<'EOF'
RALPH LOOP ITERATION {iteration_num}

TASK: {user_prompt}

1. Read progress.md
2. Do ONE task
3. Commit
4. STOP

Emit 🎯 RALPH_LOOP_COMPLETE 🎯 when done.
EOF

# Use custom outer prompt
./ralph.py "Fix bugs" --outer-prompt prompts/outer-prompt-aggressive.md
```

**Template variables:**
- `{iteration_num}` - Current iteration number
- `{user_prompt}` - User's task description

## Usage Patterns

### Local Execution

```bash
# Basic usage
./ralph.py "Fix all type errors" --max-iterations 15

# With custom outer prompt
./ralph.py "Implement auth" --outer-prompt prompts/custom.md
```

### Remote Execution

Execute Ralph against a remote repository via SSH:

```bash
# Basic remote execution
./ralph-remote.sh \
  --host dev.example.com \
  --repo https://github.com/org/repo \
  --inner-prompt "Fix all linting errors" \
  --max-iterations 20

# With SSH key and custom port
./ralph-remote.sh \
  --host dev.example.com \
  --port 2222 \
  --key ~/.ssh/id_rsa \
  --user developer \
  --repo git@github.com:org/repo.git \
  --inner-prompt-file task.md \
  --max-iterations 30

# With custom outer prompt
./ralph-remote.sh \
  --host dev.example.com \
  --repo https://github.com/org/repo \
  --inner-prompt "Test all features" \
  --outer-prompt prompts/outer-prompt-testing.md

# Test configuration (dry-run)
./ralph-remote.sh \
  --host dev.example.com \
  --repo https://github.com/org/repo \
  --inner-prompt "Test" \
  --dry-run
```

**How ralph-remote.sh works:**
1. SSH to specified host
2. Clone the repository to working directory
3. Remove git remote (prevents accidental pushes)
4. Copy Ralph script, outer prompt, and inner prompt to `.ralph/`
5. Execute Ralph with specified configuration
6. Leave results in remote working directory

**Security notes:**
- The remote's git origin is removed to prevent accidental pushes
- Results remain on the remote host for review before pushing
- Use `--dry-run` to test SSH and configuration without execution

### Human-in-the-Loop (recommended for learning)

```bash
./ralph.py "Implement auth" --max-iterations 20 --human-in-the-loop
```

### With PRD

```bash
./ralph.py "Complete all tasks in PRD.md" --max-iterations 40
```

### Quick Testing

```bash
./ralph.py "Run tests" --max-iterations 5 --quick --cli-type codex
```

## Best Practices

**Task Sizing:**
- Small focused tasks: 5-15 iterations
- Medium features: 20-40 iterations
- Large refactors: break into multiple loops

**Prompting:**
- Be specific about completion criteria
- Include quality gates in prompt
- Reference PRD files for complex work
- Define what "done" means
- Make TodoWrite usage MANDATORY
- Make progress.md updates BLOCKING (no commit without update)
- Explicitly state: "Do NOT batch multiple tasks"

**Enforcement Patterns:**
- Require git commit after each task completion
- Block commits without progress.md update
- Use TodoWrite to track exactly one in_progress task
- Stop immediately after each commit (don't continue)

**Safety:**
- Always set --max-iterations
- Start with --human-in-the-loop
- Monitor git history during pauses
- Break large tasks into phases

**PRD Structure:**
- Keep tasks small (1-3 commits each)
- Include verification criteria
- Use markdown checklists
- Phase complex features

## Implementation Reference

See [ralph.py](ralph.py) for working implementation with:
- Automatic prompt wrapping
- Completion detection
- Progress summarization
- HITL pause functionality
- Support for claude and codex CLIs

## Community Resources

The Ralph Loop pattern emerged in late 2025, with extensive community discussion about the "won't stop after one task" challenge:

**Overview & Patterns:**
- [From ReAct to Ralph Loop](https://www.alibabacloud.com/blog/from-react-to-ralph-loop-a-continuous-iteration-paradigm-for-ai-agents_602799) - Comprehensive explanation of the paradigm
- [Ralph Wiggum Explained](https://blog.devgenius.io/ralph-wiggum-explained-the-claude-code-loop-that-keeps-going-3250dcc30809) - How the loop keeps going
- [The AI Coding Loop That Won't Quit](https://www.publish0x.com/omniai/the-ralph-loop-the-ai-coding-loop-that-won-t-quit-xlegjlm) - Core concepts

**Official Implementation:**
- [Ralph Wiggum Plugin](https://www.vibesparking.com/en/blog/ai/2026-01-03-ralph-wiggum-plugin-claude-code-iterative-ai-loops/) - Anthropic's official plugin (Dec 2025)
- [Awesome Claude - Ralph Wiggum](https://awesomeclaude.ai/ralph-wiggum) - Plugin directory listing

**Problem Analysis:**
- [Claude Code: High Agency Loop](https://medium.com/@aiforhuman/claude-code-a-simple-loop-that-produces-high-agency-814c071b455d) - Why simple loops produce agency
- [2026 - Year of the Ralph Loop Agent](https://dev.to/alexandergekov/2026-the-year-of-the-ralph-loop-agent-1gkj) - Evolution and adoption

**Alternative Implementations:**
- [snarktank/ralph](https://github.com/snarktank/ralph) - Autonomous loop running until PRD complete
- [vercel-labs/ralph-loop-agent](https://github.com/vercel-labs/ralph-loop-agent) - AI SDK implementation
