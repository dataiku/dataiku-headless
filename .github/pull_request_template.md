<!-- Prose, not headers-for-header's-sake. No tables, no restating the diff,
     no meta-commentary about the PR itself. -->

## Summary

<!-- What changed and why, in a couple sentences. Link any related issues. -->

## Agent impact (optional — skip if Summary already covers it)

<!-- How does this change make agents more successful?
     Examples: clearer error messages, new --help output, reduced ambiguity. -->

## Test plan

Local checks (see [CONTRIBUTING.md](../CONTRIBUTING.md#local-checks)):

- [ ] Tests, lint, and quality ratchet pass.
- [ ] Security scan (`bandit`) and dependency audit (`make audit`) pass.
- [ ] `make test-plugin` passes (if MCP packaging changed).
- [ ] Manual smoke test performed (describe):

---

_By submitting this pull request, I agree to the [Apache 2.0 license](LICENSE)._
