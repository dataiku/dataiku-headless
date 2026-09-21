# Contributing to `dataiku-headless`

Thank you for helping improve `dataiku-headless`.

## Before making a change

- Search the existing issues before opening a new one.
- Use the issue forms for bugs, usage questions, and feature proposals.
- For a substantial change, open a feature proposal before starting implementation
  so the scope can be agreed. Small fixes can go directly to a pull request.

Read [`CODING_STANDARDS_AND_STRUCTURE.md`](CODING_STANDARDS_AND_STRUCTURE.md)
before changing code. It documents the repository structure, implementation
conventions, validation requirements, and pull request checklist.

## Large changes

Keep changes concise. For a major architectural change, or one that adds or
changes more than roughly 500 lines of implementation code, open a GitHub RFC
before requesting review. The RFC should discuss the technical design and its
justification, then be linked from the pull request.

Documentation, tests, generated lockfiles, and mechanical formatting changes do
not by themselves trigger this expectation. Maintainers may apply the
`rfc-required` label to a pull request and defer review until the RFC is
discussed.

## Opening a pull request

1. Fork the repository and create a focused branch from `main`.
2. Make the smallest coherent change and add or update relevant tests.
3. Run the verification commands in the coding standards linked above.
4. Open a pull request against `main`.

Use a [Conventional Commits](https://www.conventionalcommits.org/) title for the
pull request, such as `fix: handle failed plugin installation`. In the pull
request description, summarize the behavior changed and list the checks you ran,
including any checks you could not run and why.

Never include credentials, customer data, instance URLs, exports, local
configuration, or identifiers copied from a real Dataiku environment.
