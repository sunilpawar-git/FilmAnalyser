# Security review (Phase 8)

Scope: a local command-line tool. It reads a film file the user names, runs `ffmpeg` and `ffprobe`
on it, writes a Parquet store and a static HTML report into folders the user names. No server, no
network at run time, no accounts. The inputs an attacker could control are the **film file** (its
bytes and its name) and the **paths and options** on the command line.

## Automated checks (all part of `make check`)

| Check | Result on this tree |
|---|---|
| `bandit` with the project config (`B404`/`B603` skipped) | no findings |
| `bandit` with **no** skips, `-r src scripts` | 15 findings, all Low and all `B404`/`B603` ("subprocess is used", "argument-list subprocess"): 0 Medium, 0 High. Every call takes an argv list built by a `*_argv` function; no `shell=True` (shell variants B602, B604 to B607 stay enabled and are clean) |
| `pip-audit --require-hashes` on the locked runtime and dev set | no known vulnerabilities |
| `pip-licenses` allowlist (permissive licences only) | pass (`0BSD` added for `chardet`, a dev-only dependency of the SBOM tool) |
| `gitleaks` | no leaks |
| `tests/architecture/test_security_patterns.py` | no `shell=True`, `pickle`, `eval`, `exec`, `requests`/`urllib`, no security suppression comments |
| Guard self-test | each rule is proven to fail on a planted violation |

## Dependency pins

- Runtime dependencies (`jinja2`, `numpy`, `pyarrow`, `onnxruntime`) are declared with lower bounds
  (`onnxruntime` exactly) and **resolved to exact versions with hashes in `uv.lock`**. The supported
  install is `uv sync --locked`, which installs exactly those and refuses a hash mismatch; CI does
  the same. A user who installs the wheel with `pip` gets the newest versions that satisfy the
  bounds, which is normal for a library and is not covered by the lock.
- The build backend is pinned (`hatchling==1.27.0`). GitHub Actions are pinned to commit SHAs
  (a test enforces it) and kept current by Dependabot. `ffmpeg` is pinned by version and checksum in
  CI. The two model files are pinned by SHA-256 and verified before use.
- Dev-only additions this phase: `cyclonedx-bom` (SBOM) and its dependencies; they do not ship in the
  wheel (the SBOM lists the runtime set only).

## Manual review

**Command injection.** The only processes started are `ffmpeg`, `ffprobe` (and, opt-in, `demucs`),
always as an argument list, never through a shell. The film path is resolved to an absolute path
first (it cannot start with `-`), and is also placed after `--`. `test_hostile_names.py` runs films
named `$(touch PWNED); ... #.mp4` and `-i.mp4` through the real command: nothing runs, nothing is
read as an option. Argv builders are the only way a command is made (architecture test).

**Path traversal and overwrite.** Store files are named from integers and a fixed manifest name,
written only inside the resolved output folder, atomically, and a symlink in place of a store file
is refused. The report is written the same way and the command refuses a report path that is the
film itself (also through a link), a link, or in a folder that does not exist, *before* the analysis
starts. `--fresh` deletes only the manifest, chunk files and stale temp files, never a link, never a
subfolder (tests, with guard mutations). A film named `..%2f..%2fescape.mp4` writes nothing outside
the output folder.

**Report XSS.** Jinja2 with autoescape on and `StrictUndefined`; no template uses `|safe` (test);
the only untrusted text on the page is the film's file name, which appears as escaped text; charts
are numbers turned into SVG coordinates by code, not strings from the film. The page carries
`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`: no script, no network, no
external resource, even if escaping failed. A film named `<img src=x onerror=alert(1)>"'.mp4` renders
as text (test).

**Terminal output.** A file name is attacker-controlled text that the command prints. *Finding:*
messages contained the name unfiltered, so a name holding a terminal escape sequence or a newline
could rewrite the screen or forge a line. *Fixed:* every printed message has control characters
replaced (`cli/main.py`); tested with a name holding `ESC[2J` and a newline, with a guard mutation.
Log events (`-v`) are JSON, which escapes control characters by itself.

**Hostile films.** ffmpeg and ffprobe parse the media; the tool bounds their output (4 KB of
stderr, 1 MB of probe output), their run time (timeouts), and reads store files with a size limit.
Memory is bounded by the chunk, not the film (see the handoff for the measured peak). A bug in ffmpeg
itself is outside what this tool can mitigate: keep ffmpeg current when analysing files you do not
trust.

## What this review does not cover

- Windows (untested). Installers and code signing (post-MVP).
- A malicious `demucs` executable on `PATH` (opt-in; it is run as the user, like ffmpeg).
- Supply-chain compromise of a dependency before it enters `uv.lock`: pins and hashes stop a later
  swap, not a first poisoned release.
