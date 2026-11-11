# Branch protection for `main`

Protection is a GitHub-side setting, so it can only be applied once the repository exists on
GitHub. Applied on 2026-11-11 (DECISIONS #41); the repo had to be made public for it.

## 1. Create the remote and push (private; films and data never go here)
```sh
gh repo create FilmAnalyser --private --source . --remote origin
git push -u origin main --tags
```

## 2. Let CI run once
The required check names only become selectable after the workflow has run on GitHub. Wait for
`ci` to finish on `main` (it must be green on both OSes before protecting).

## 3. Protect `main`
Merge only when CI is green, even when working alone: required status checks, no force-push, no
deletion, linear history, enforced for admins. No required reviewer (solo project).
```sh
OWNER_REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api -X PUT "repos/${OWNER_REPO}/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["make check (macos-latest)", "make check (ubuntu-latest)"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```
Note: branch protection on a **private** repository needs a paid GitHub plan (Pro or higher). On
the free plan, make the repo public or use rulesets on a plan that supports them.

## 4. Verify
```sh
gh api "repos/${OWNER_REPO}/branches/main/protection" --jq '.required_status_checks.contexts'
git push origin main   # a direct push of an unchecked commit must now be rejected
```

## Day-to-day flow
Trunk-based: short-lived branch -> PR -> CI green -> squash/rebase merge. Commit messages follow
Conventional Commits (`feat(foundation): ...`); the `commit-msg` hook (`make hooks`) checks them.
