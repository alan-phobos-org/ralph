# Agent Instructions

## What This Is

Ralph Loop: iterative AI agent execution pattern. Feeds same prompt repeatedly to AI until task complete. Progress persists in files/git, not context.

**Core principle:** Naive persistence beats sophisticated complexity.

## Files

- [ralph.py](ralph.py) - Current implementation (preferred)
- [ralph-old.py](ralph-old.py) - Original implementation (reference)
- [RALPH.md](RALPH.md) - Comprehensive documentation and patterns

## Key Mechanisms

1. **External verification** - Agent reviews own work each iteration, identifies gaps, improves
2. **Self-correcting** - Each iteration sees previous changes via git/files, fixes bugs
3. **Fresh context** - When context fills, fresh agent continues from file state
4. **File system = truth** - Git history + files persist; LLM memory does not

## Implementation Pattern

Agent receives wrapped prompt with mandatory workflow:
1. Read progress.md (ground truth)
2. Do ONE task only
3. Run quality gates (tests/types/lint)
4. Update progress.md
5. Commit work + progress.md
6. STOP (loop re-invokes for next task)

Forced constraints:
- Low max-turns (8) prevents overwork
- Aggressive timeout (180s)
- Commit detection forces continuation
- Mechanical limits beat prompt compliance

## GIT COMMITS

**DO NOT CREATE GIT COMMITS.**

User manages all git operations. Focus on code changes only.

## Your Role

When working in this repo:
- Analyze/improve ralph loop implementation
- Test/verify script functionality
- Keep docs accurate (RALPH.md, AGENTS.md)
- Propose improvements to wrapper prompts or constraints
- NO commits - user handles git
