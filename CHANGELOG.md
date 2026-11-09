# Changelog

## 1.2.3 — unreleased

- Fix fail-open on missing policy (CVE-pending: 1.2.2 and earlier allowed destructive
  operations when `.axiom/invariants.yaml` did not exist). A missing policy now loads
  a built-in default that blocks destructive shell commands (`rm -rf` outside the
  project, force-push, `DROP`/`TRUNCATE`, disk-level tools such as `dd`/`mkfs`,
  shell redirects to auth files) and writes to auth/credential files (`~/.ssh/`,
  `~/.aws/credentials`, `.env`, `/etc/passwd`, `/etc/shadow`, …), and lets
  everything else through. A one-line notice identifies the active policy and how
  to customize it.
- Deny intercepted operations when policy is empty, unreadable, malformed or unsupported;
  print recovery instructions.
- Deny unexpected hook errors and invalid input.
- Install the complete payload from the same checkout; derive version from pyproject.toml.
- Declare zero runtime dependencies and contributor extras.
- Add policy-state regression tests and Python CI matrix.

No prior pyproject.toml existed. The initial project version was established by incrementing the latest existing git tag's patch component; future versions derive from pyproject.toml.
