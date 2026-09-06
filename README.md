# antenati

[![PyPI version](https://img.shields.io/pypi/v/antenati)](https://pypi.org/project/antenati/)
[![Python versions](https://img.shields.io/pypi/pyversions/antenati)](https://pypi.org/project/antenati/)
[![License: GPL-3.0-or-later](https://img.shields.io/pypi/l/antenati)](https://github.com/gcerretani/antenati/blob/master/LICENSE)
[![CI](https://github.com/gcerretani/antenati/actions/workflows/ci.yml/badge.svg)](https://github.com/gcerretani/antenati/actions/workflows/ci.yml)

`antenati` downloads the digitised pages of a **single gallery/register** from the Italian [Portale Antenati](https://antenati.cultura.gov.it/), using the IIIF manifest exposed by the portal.

One invocation resolves one gallery or direct Antenati manifest, builds a deterministic download plan and writes the selected pages to disk. It does **not** recursively mirror an Archivio di Stato, a municipality, or search results from the portal.

## Highlights

- **Full-resolution or resized images** — request the original IIIF image size or a bounded size.
- **Deterministic filenames** — numeric page labels are zero-padded from the complete gallery size, and collisions are resolved deterministically.
- **Verified image writes** — supported image MIME types and file signatures are checked before the temporary file is atomically promoted to its final filename.
- **Verified resume** — existing files are reused only when provenance, requested resolution, byte size and SHA-256 still match.
- **Persistent provenance** — each completed run stores the source manifest plus a per-image JSON index with canvas/source mapping, size and hash.
- **Bounded execution** — image bodies are streamed, in-flight work is bounded and explicit resource ceilings protect against anomalous sources.
- **Preview mode** — inspect the exact pages, source URLs and output filenames before image files are written.
- **CLI and GUI** — both use the same core configuration and validation rules.
- **Cross-platform** — Windows, macOS and Linux; install with `pip` or use a release executable when available.

## Installation

Install from PyPI:

```text
pip install antenati
```

Python **3.10 or newer** is required. The package installs:

- `antenati` — command-line interface
- `antenati-gui` — Tk desktop interface

Standalone GUI executables for supported platforms are attached to GitHub releases when produced by the release workflow.

## Supported inputs

The supported source is the **Portale Antenati** and the IIIF structures currently emitted by it. You can pass either:

1. an Antenati gallery URL, for example:

   ```text
   https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x
   ```

2. the direct IIIF manifest URL exposed by that gallery, for example a URL under `dam-antenati.cultura.gov.it/.../manifest`.

`antenati` is IIIF-based internally, but it is **not currently a generic IIIF downloader**. Broader Presentation/Image API variants may be unsupported even when they are valid IIIF.

## Command line

Basic use:

```text
antenati https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x
```

By default the output directory is derived from the register metadata. Use `--output` to select an exact destination path.

### Core options

| Option | Description |
|---|---|
| `-s`, `--size N` | Maximum image size in pixels; `0` requests full resolution. |
| `-n`, `--nthreads N` | Maximum number of image workers. |
| `-f`, `--first N` | Zero-based index of the first page to include. |
| `-l`, `--last N` | Zero-based exclusive end index. |
| `-d`, `--descriptive-names` | Include archive/image identifiers in filenames. |
| `-o`, `--output PATH` | Exact output directory. |
| `--existing {error,overwrite,skip,resume}` | Policy when the output already exists. Default: `error`. |
| `--dry-run` | Resolve the source and print the planned pages/filenames without downloading image bodies or creating the output directory. |
| `--verbose` | Increase logging verbosity; repeat for DEBUG. |
| `-v`, `--version` | Print the version and exit. |

Run `antenati -h` for the authoritative option list.

### Existing-output policies

- `error` — conservative default; refuse an existing output directory.
- `overwrite` — allow the run to replace planned destination files through atomic writes.
- `resume` — verify indexed existing files and redownload only missing, stale, mismatched or corrupt pages.
- `skip` — reuse only files that can be verified from the provenance index; ambiguous unverified files are never silently accepted.

The same source canvas receives the same planned filename regardless of the selected subset, worker count or completion order. For example, a 150-page gallery uses names such as `pag-001.jpg`; downloading only pages 7–12 still produces the corresponding zero-padded names from the complete gallery.

## Provenance and integrity

A completed output directory contains the downloaded images plus:

- `.antenati-manifest.json` — the source IIIF manifest captured for the run;
- `.antenati-index.json` — per-image provenance including source/canvas URL, label, filename, requested size, byte size, SHA-256 and download timestamp.

An image is counted as completed only after its response is streamed to a temporary file, the supported image format/signature is validated, the file is flushed, and the temporary path is atomically replaced into its final destination. `DownloadReport` separately tracks expected, attempted, completed, skipped, failed and cancelled work.

These checks improve local integrity; they do not cryptographically authenticate data supplied by the remote archive itself.

## CLI / GUI capability parity

| Capability | CLI | GUI |
|---|:---:|:---:|
| Gallery or direct manifest input | yes | yes |
| Page range | yes | yes |
| Image size | yes | yes |
| Worker count | yes | yes |
| Descriptive filenames | yes | yes |
| Exact output directory | yes | yes |
| Existing-output policy | yes | yes |
| Verified resume | yes | yes |
| Shared validation/reporting | yes | yes |
| Dry-run preview | yes | not yet |

Dry-run is currently a CLI review surface; the underlying download plan is shared and can support a future GUI preview without changing execution semantics.

## Graphical interface

Launch:

```text
antenati-gui
```

![GUI Screenshot](https://raw.githubusercontent.com/gcerretani/antenati/master/docs/gui_screenshot.png)

Paste a gallery/manifest URL, choose the **exact destination directory**, then select the page range, image size, thread count, descriptive-name option and existing-output policy. The GUI runs the same downloader configuration, validation and result model as the CLI.

## AWS WAF and live-site limitations

The public gallery HTML can be blocked for automated clients by the portal's AWS WAF. This can happen even while the direct manifest and IIIF image backends remain reachable.

If a gallery URL fails with an AWS WAF challenge or HTTP 403:

1. open the gallery in a browser;
2. copy its **IIIF manifest** link from the portal interface;
3. pass that manifest URL directly to `antenati` or the GUI.

The repository's scheduled live checks intentionally test gallery HTML, direct manifest access and image download as separate canaries so a frontend/WAF failure does not hide backend status.

The Portale Antenati is a third-party service and may change availability, HTML, metadata or IIIF structures without notice. The normal offline test suite verifies the structures supported by this project; it cannot guarantee future portal compatibility.

## Cancellation and resource limits

Cancellation prevents queued work from being started where possible. Requests already active are bounded by HTTP connect/read timeouts rather than being forcibly terminated at an arbitrary byte boundary.

The downloader also applies ceilings to metadata size, image size, canvas count, total downloaded bytes and in-flight work. These are safety limits, not claims about maximum IIIF sizes in general.

## License

Released under the [GNU General Public License v3 or later](https://www.gnu.org/licenses/gpl-3.0.html).

See the [changelog](https://github.com/gcerretani/antenati/blob/master/CHANGELOG.md) for release history and the [issue tracker](https://github.com/gcerretani/antenati/issues) for known limitations and planned work.
