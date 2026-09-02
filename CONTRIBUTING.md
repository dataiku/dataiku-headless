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
