# Security

## Reporting a vulnerability

Please **do not** open a public issue. Email the maintainers or open a
[private vulnerability report](https://github.com/<owner>/gitundo/security/advisories/new)
on GitHub.

We aim to acknowledge reports within 3 business days and to ship fixes for
confirmed issues promptly.

## Design notes

* gitundo runs the git commands *you* would run and never enables unsafe
  flags; destructive patterns are matched conservatively.
* Checkpoint commits are authored `gitundo <gitundo@localhost>` so malicious
  or accidental content can never be attributed to your real identity.
* The auto-guard passes commands through untouched if anything fails — it
  never blocks or rewrites your input.
