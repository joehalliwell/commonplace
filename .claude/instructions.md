# Claude Code Instructions for Commonplace

## Code Changes Requirements

### 1. Self-Contained Proposals
When proposing code changes:
- Present the full context of what you're changing and why
- Show complete before/after code blocks for significant changes
- Explain the rationale and any trade-offs
- Include usage examples if adding new features or APIs

### 2. Test Coverage
**All code changes MUST include tests:**
- New features require new test cases demonstrating the functionality
- Bug fixes require regression tests that would fail without the fix
- Refactoring should maintain or improve existing test coverage
- Use pytest and follow the existing test structure in `tests/`

### 3. Test Standards
- Place tests in appropriate files (e.g., `test_search.py` for search features)
- Use descriptive test names: `test_<feature>_<scenario>_<expected_result>`
- Include both positive and negative test cases
- Use fixtures from `conftest.py` when appropriate
- Add snapshot tests for complex output formats when relevant

### 4. Code Quality
- Follow existing code style (Ruff formatting, type hints)
- Keep functions focused and well-documented
- Use type hints consistently
- Add docstrings for public APIs
- Update README.md if user-facing features change

## Commit Messages
- Keep commit messages concise and focused
- Use imperative mood ("Add feature" not "Added feature")
- Do NOT add credits, co-author tags, or AI generation notices
- Follow the existing commit style in the repository

## Example Workflow

When implementing a new feature:
1. Describe the proposed change and get confirmation
2. Write the implementation code
3. Write comprehensive tests
4. Run tests to verify: `uv run pytest tests/ -v`
5. Format code: `uv run ruff format .`
6. Update documentation if needed

When fixing a bug:
1. Write a failing test that reproduces the bug
2. Fix the bug
3. Verify the test now passes
4. Ensure no other tests broke
