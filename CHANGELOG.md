# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.0] - Unreleased

### Added
- Verified resume support that reuses existing files only when provenance, requested resolution, byte size and SHA-256 still match (#59)
- Structured `DownloadReport` shared by CLI and GUI, with expected, attempted, completed, skipped, failed and cancelled state (#60)
- Persistent `.antenati-manifest.json` and `.antenati-index.json` provenance with per-image canvas/source mapping, requested size, byte size, SHA-256 and timestamp (#61)
- Explicit output selection and `ask`, `error`, `overwrite`, `skip` and `resume` existing-output policies in CLI and GUI; `ask` is the shared interactive default and recommends verified resume (#62)
- CLI `--dry-run` preview of the exact planned pages, filenames and image URLs without image writes (#63)
- Shared CLI/GUI configuration model, including worker-count and descriptive-filename controls in the GUI (#64)
- Resource ceilings for metadata, image size, canvas count, total bytes and bounded in-flight work (#50)

### Changed
- Split downloader construction, source loading, planning and execution into explicit phases; constructing a `Downloader` no longer performs network I/O (#67)
- Numeric page labels are zero-padded from the complete gallery size so lexicographic filename order matches page order and remains stable across subsets (#73)
- Image bodies are streamed instead of buffered in memory, and queued work is bounded relative to worker count (#50)
- CLI, GUI and programmatic execution now share preflight validation for page ranges, image size and worker count (#52)
- README now documents standalone GitHub Release executables as the recommended path for non-Python users, alongside PyPI and source/development installation, and describes the actual single-gallery/register scope and integrity guarantees (#68)

### Fixed
- Reject unsupported media types, HTML/text responses, corrupt image data and MIME/signature mismatches before a final image file is committed (#47)
- Missing or invalid response metadata and malformed selections now fail with controlled domain errors instead of late technical exceptions (#52)
- Existing files are never silently treated as valid by resume/skip semantics without matching provenance and integrity checks (#59, #62)
- Restored interactive handling of non-empty output directories through the explicit `ask` policy instead of failing by default (#62)

### Testing
- Expanded offline regression coverage for cancellation side effects, filename collisions and padding, atomic/integrity guarantees, report/file consistency, provenance, verified resume, output policies, resource limits and shared configuration (#66)

## [6.2] - 2026-09-06

### Fixed
- Prevent silent overwrites when multiple canvases normalize to same default filename; later collisions now receive deterministic suffixes
- Add bounded HTTP connect/read timeouts and ensure a cancellation already requested before `run()` performs no image requests
- Write downloads through temporary files and atomically replace the destination only after a complete write, preserving existing good files on write failures and avoiding symlink-following writes
- Fix a Tk GUI race where the terminal `Done`/`Failed`/`Cancelled` event could remain unprocessed after the worker exited
- Parse Antenati archive IDs and `manifestId` assignments structurally, including URLs with explicit ports
- Rewrite the IIIF size component structurally so valid source forms such as `max` are handled correctly
- Make the scheduled live-download canary report failures at workflow-run level instead of appearing green
- Preserve executable permissions in packaged macOS/Linux release archives

### Added
- Regression tests for duplicate canvas labels, preset cancellation, archive URLs with explicit ports, `manifestId` binding, and IIIF `max` size rewriting

## [6.1] - 2026-06-12

### Added
- Automated GitHub release creation in CI/CD pipeline: the release workflow now packages the PyInstaller binaries as zip assets and publishes the GitHub release automatically on tag push

### Changed
- Relicensed from MIT to GPL-3.0-or-later; all source files carry SPDX-FileCopyrightText / SPDX-License-Identifier headers
- Rewrote README for PyPI-first presentation: `pip install antenati` as the primary installation method, highlights section, CLI options table, fixed screenshot URL for PyPI rendering
- Removed `PRINCIPIANTI.md` (superseded by the updated README)

## [6.0] - 2026-06-11

### Added
- Comprehensive test suite (15+ test modules) covering IIIF parsing, HTTP handling, download orchestration, filesystem operations, and end-to-end flows with mocked HTTP
- Typed exception hierarchy (`ManifestError`, `WafChallengeError`, `ThreadError`) replacing generic `RuntimeError`
- `--verbose` / `-vv` flags to control log verbosity (WARNING → INFO → DEBUG)
- Automatic exponential backoff retry policy for transient 5xx and rate-limit (429) responses

### Changed
- Dropped Intel macOS (macOS 13) binary artifacts: GitHub Actions no longer provides Intel macOS runners; only Apple Silicon (macOS 14, arm64) is now built
- Refactored monolithic `antenati.py` into a modular package structure under `src/antenati/`:
  - `downloader.py`: core `Downloader` class with thread-pool orchestration
  - `iiif.py`: pure IIIF manifest parsing helpers (no I/O, offline-testable)
  - `http.py`: HTTP session building and request handling
  - `errors.py`: typed exception hierarchy
  - `cli.py`: CLI entry point with logging configuration
- CI/CD pipeline updated with linting (ruff), type checking (mypy), and offline test runs

## [5.0] - 2025-11-01

### Added
- Restored support for full/resolution image size downloads

### Changed
- Default requested size is now `0` (maximum available size) instead of 1000 pixels; use `--size N` to limit size

### Fixed
- Graceful handling of server denials (403 or WAF challenge)

## [4.0] - 2025-07-27

### Changed
- Updated implementation to comply with recent SAN server filter requirements:
  - Full-resolution downloads are no longer supported; this may be revisited in future releases
  - Users must now specify the maximum image size using the `-s/--size` option (default: 1000 px); requests for larger images will result in a 403 error
  - Download logic now detects AWS WAF challenges and provides a clear error message, replacing the previous generic 202 error; no workaround is currently available
  - Reduced default number of threads and connections to minimize server load
  - Updated the user agent string to a modern value
- Replaced the use of the `urllib3` Python module with the more flexible `requests` library
- Removed the `-c/--nconn` parameter; connection management now relies on the defaults provided by the `requests` library

## [3.2] - 2025-07-14

### Fixed
- Access to IIIF manifest with proper HTTP headers to address recent changes in SAN server filters that broke v3.1

### Changed
- Download size now reported in binary format (MiB rather than MB)
- Update Python dependencies

## [3.1] - 2025-02-08

### Added
- Pyinstaller artifacts now built with Python 3.12
- Support for multiple platforms:
  - Ubuntu 22.04 (x86_64)
  - macOS 13 (Intel)
  - macOS 14 (arm64)
  - Windows 2022

### Changed
- Minimum Python version moved to 3.9
- Improved README documentation

## [3.0] - 2024-10-14

### Added
- New GUI available with `antenati_gui.py`
- GUI standalone executables generated by pyinstaller
- Support for Windows, macOS and Linux standalone executables

## [2.5] - 2023-01-22

### Fixed
- Support for new URL [antenati.cultura.gov.it](https://antenati.cultura.gov.it/)

## [2.4] - 2022-12-28

### Added
- Possibility to set range of pages to download using `-f` and `-l` options
- Type hints throughout the codebase

### Fixed
- Removed usage of deprecated `cgi.parse_header`

## [2.3] - 2022-05-21

### Added
- HTTP headers to get around SAN server filters

## [2.2] - 2022-02-16

### Changed
- Several minor improvements

## [2.1] - 2021-11-20

### Changed
- Code restyle with argument parsing to specify number of threads and number of connections

## [2.0] - 2021-11-19

### Added
- Support for new Portale Antenati (Fall 2021)

## [1.1] - 2019-10-12

### Changed
- Upgraded to Python 3 using 2to3 tool

## [1.0] - 2019-04-14

### Added
- First stable release
