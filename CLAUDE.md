# CLAUDE.md

Project instructions for Claude Code. Read this at the start of every session.

## Project
Data science project with a Python + FastAPI backend.

## Stack
- Language: Python
- Framework: FastAPI
- Package manager: uv
- Testing: none (skipped for now)

## Commands
- Install deps: `uv sync`
- Run server: `uv run fastapi dev`
- Add package: `uv add <package>`

## Code Style
- No semicolons
- Clean, well-structured code
- Comment where logic isn't self-evident; do not overcomment
- Consistent formatting throughout

## Claude Behavior
- Work agentically — make changes directly without narrating every step
- Keep responses concise
- Ask before proceeding only when a key assumption could significantly affect direction
- Commit and push on my behalf when work is complete
- Never add unnecessary boilerplate, over-engineer, or add features not requested
