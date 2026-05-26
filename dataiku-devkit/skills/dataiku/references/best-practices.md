# Best Practices & Design Patterns

Use this entrypoint to choose the right production-quality plugin guidance.

| Need | Read |
|---|---|
| Architecture, error handling, performance, logging, data modeling, security, anti-patterns | `plugin-production-patterns.md` |
| Plugin tiers and architecture choices | `plugin-architecture.md` |
| Component-specific patterns | `recipes.md`, `llm-tools.md`, `webapps.md`, `parameters.md`, `testing.md` |

## Checklist for Production Plugins

### Before Release

- [ ] All tests passing (unit + integration)
- [ ] Code linted (ruff/mypy clean)
- [ ] Dependencies pinned in requirements.txt
- [ ] Version bumped in plugin.json
- [ ] README updated with new features
- [ ] CHANGELOG updated
- [ ] All secrets removed from code
- [ ] Error messages are user-friendly
- [ ] Logging is appropriate (not too verbose)

### Documentation

- [ ] plugin.json has clear labels and descriptions
- [ ] All parameters have descriptions
- [ ] Recipe/tool inputs/outputs are documented
- [ ] Examples provided where helpful

### Security

- [ ] Input validation on all user inputs
- [ ] SQL injection prevention (if applicable)
- [ ] Credentials stored in plugin config (not code)
- [ ] No sensitive data in logs

### Performance

- [ ] Large datasets handled with streaming
- [ ] Parallelization for batch operations
- [ ] Appropriate timeouts configured
- [ ] Memory-efficient processing
