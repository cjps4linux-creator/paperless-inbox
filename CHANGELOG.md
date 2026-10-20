# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-10-20

### Added

- **Real CI test gate.** The workflow ran `pytest -q || echo "No tests yet"`,
  which executes no tests and always exits zero. It is replaced with a
  pinned `pytest==8.3.3` installation and an unconditional `pytest -q`.
  The suite has 55 tests.
- **Dependency pin guard** (`scripts/pin_guard.py`), wired as a required
  `pin-check` status check.

### Fixed

- **Receipt loss on filename collision.** A new receipt whose filename
  matched an existing one silently overwrote it. The watcher now preserves
  both by adding a numeric suffix, and the behaviour is covered by a
  regression test.
- **False merge success.** A failed merge was reported as successful. The
  merge script now reports `combine failed:` and exits non-zero, and the
  test asserts the exit code.
- **Launcher scripts are location-independent.**

### Changed

- The Ruff rule set is pinned to `E4,E7,E9,F` with `ruff==0.17.1`.
- The `tmp_path` guard assertion is platform-independent.
- **README author credit** added: Conrad CJ Wilson.

### Security

- Secret scanning and push protection enabled at the repository level.

## [0.1.0]

- Initial release: receipt and invoice capture, batch merge to PDF

[1.0.0]: https://github.com/cjps4linux-creator/paperless-inbox/releases/tag/v1.0.0
