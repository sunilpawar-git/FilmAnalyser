# Releasing

A release is a `v*` tag on `main`. The `release` workflow then runs the same suite as every pull
request (`ci.yml`, macOS and Linux), builds the wheel, makes the CycloneDX SBOM and `SHA256SUMS`,
installs the wheel into a fresh environment and analyses a synthetic film with it, and only then
publishes the GitHub release (the one job with write access) with the changelog section as notes.

1. Merge everything for the release to `main`; `make check` is green.
2. Pick the version: update `version` in `pyproject.toml` (Conventional Commits: `feat` is a minor
   bump, `fix` a patch, `!` or `BREAKING CHANGE` a major) and `uv lock`.
3. Cut the changelog section: `uv run cz changelog --unreleased-version X.Y.Z` (rewrites
   `CHANGELOG.md` from the commits). Commit both through a pull request.
4. After it is merged: `git tag vX.Y.Z && git push origin vX.Y.Z`.
5. The workflow refuses a tag that is not `v` plus the `pyproject.toml` version, or a changelog with
   no entries under that version (`scripts/release_notes.py`).

Check the pieces without a tag: `make release-assets` (wheel, SBOM and checksums in `dist/`) and
`uv run python scripts/release_notes.py vX.Y.Z`.
