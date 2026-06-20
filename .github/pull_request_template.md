# Pull Request

## Summary
<!-- 1-3 bullets describing what changed and why. -->

## Changes
- 

## Test plan
- [ ] CI green (ruff, mypy --strict, pytest, eslint, build)
- [ ] If touching auth/RLS: tested cross-user isolation manually
- [ ] If touching the Postgres schema: alembic upgrade then downgrade then upgrade roundtrip passes
- [ ] If touching the IDE bundle hosting: confirmed the iframe loads + CSP unchanged
- [ ] CHANGELOG entry under `[Unreleased]`

## Security review
- [ ] No new secrets logged
- [ ] No `eval`/`exec`/`subprocess(shell=True)` of user input
- [ ] All new mutating routes have a CSRF token + RLS-context middleware

---
By submitting this PR, I confirm I am the author or have rights to contribute the change. License: Apache-2.0.
