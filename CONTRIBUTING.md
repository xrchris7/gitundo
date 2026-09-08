# Contributing to gitundo

Thanks for helping! This is a small, dependency-free codebase on purpose —
please help keep it that way.

## Dev setup

```bash
git clone <your-fork> && cd gitundo
python -m pip install -e ".[dev]"      # or: pip install -e . pytest
python -m pytest                        # run the suite
```

Requires Python ≥ 3.9 and a `git` binary on `PATH`. All tests run against
real throwaway git repositories in a temp directory — no mocks, no network.

## Project layout

```
src/gitundo/
  core.py      # engine: snapshot / restore / diff / prune / guard / autowrap
  cli.py       # argparse CLI + output formatting (thin layer over core)
  __init__.py  # version + constants
tests/         # pytest suite (conftest.py builds real repos)
docs/          # human documentation
contrib/completions/
```

## What makes a good PR

1. **Small and focused.** One feature or fix per PR.
2. **Tests for real git behaviour.** Prefer an assertion against a
   throwaway repo over a mock.
3. **Documentation.** If you add a flag, mention it in `docs/CLI.md` and the
   README command table.
4. **Zero new runtime dependencies.** The standard library + git is a feature.

## Ideas welcome

Known good directions (open an issue first to discuss):

* Shell guards for fish / PowerShell / Windows.
* Pre-commit / IDE / editor integrations.
* More destructive-command patterns (with conservative false-positive rules).
* Push-to-remote helper (`gitundo push` / `pull` for the checkpoint ref).
* Diff/merge helpers and a `gitundo log --graph`.

## Commit messages

Follow conventional commits loosely: `feat:`, `fix:`, `docs:`, `test:`,
`refactor:`. Include a `Closes #N` when relevant.
