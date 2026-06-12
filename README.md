# antenati

[![PyPI version](https://img.shields.io/pypi/v/antenati)](https://pypi.org/project/antenati/)
[![Python versions](https://img.shields.io/pypi/pyversions/antenati)](https://pypi.org/project/antenati/)
[![License: GPL-3.0-or-later](https://img.shields.io/pypi/l/antenati)](https://github.com/gcerretani/antenati/blob/master/LICENSE)
[![CI](https://github.com/gcerretani/antenati/actions/workflows/ci.yml/badge.svg)](https://github.com/gcerretani/antenati/actions/workflows/ci.yml)

**The only tool that lets you download full-resolution images from the
*[Portale Antenati](https://antenati.cultura.gov.it/)*, the genealogy digital
archive of the Italian *Ministero della Cultura*.**

The Portale Antenati hosts millions of digitised civil and parish records, but
its web viewer only lets you look at one page at a time — and the servers slow
to a crawl in the evening. `antenati` reads the standard
[IIIF](https://iiif.io/) manifest behind each gallery and downloads **every
image of an entire archive in one shot, at the highest resolution available**,
with no clicking and no waiting. Launch it, grab a coffee, and come back to a
folder full of records ready for your family tree.

## Highlights

- 🖼️ **Full-resolution downloads** — the only tool that still retrieves images at maximum size from the portal.
- 📚 **Whole archives at once** — point it at a gallery and it fetches every page automatically.
- ⚡ **Fast & parallel** — multi-threaded downloads with automatic retry/backoff on transient errors.
- 🖥️ **CLI *and* GUI** — a scriptable command line and a friendly desktop window, from the same package.
- 🧩 **IIIF-native** — works directly with the portal's IIIF manifests, so it keeps working when the web viewer changes.
- 🌍 **Cross-platform** — Windows, macOS and Linux; install with `pip` or grab a standalone executable.

## Installation

The recommended way to install `antenati` is from [PyPI](https://pypi.org/project/antenati/):

    pip install antenati

This requires **Python 3.10 or newer** and gives you two commands on your `PATH`:

- `antenati` — the command-line downloader
- `antenati-gui` — the graphical interface

> On Windows the Python build from the Microsoft Store works fine; on Linux use
> your distribution's package manager to get Python first.

### Standalone executables (no Python needed)

If you'd rather not install Python and `pip` at all, prebuilt standalone
executables of the **GUI** for Windows, macOS and Linux are attached to every
release. Just download the one for your system from the
[latest release artifacts](https://github.com/gcerretani/antenati/releases/latest)
and run it — no installation required.

## Usage

### Command line

Pass the URL of a gallery page (or of its IIIF manifest) to the `antenati` command:

    antenati <URL of the album>

The images are saved to a new folder named after the archive, in the form
*ARCHIVE-PLACE-YEAR-TYPE-ID*.

**Example** — to download the people born in Viareggio in 1807, find the
gallery page on the portal:

[https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x](https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x)

then copy the link to the first page and pass it to the tool:

    antenati https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x

The results land in a folder named
*archivio-di-stato-di-lucca-stato-civile-napoleonico-viareggio-1807-nati-19944549*.

If you didn't install the package, you can still run it as a module:

    python3 -m antenati <URL of the album>

#### Options

| Option | Description |
|---|---|
| `-s`, `--size N` | Image size in pixels (`0` = full size, the default). |
| `-n`, `--nthreads N` | Maximum number of download threads. |
| `-f`, `--first N` | Index of the first image to download. |
| `-l`, `--last N` | Index of the first image *not* to download. |
| `-d`, `--descriptive-names` | Include the archive and image IDs in the file names (e.g. `pag-1+an_ua19944535+w9DWR8x.jpg`). |
| `--verbose` | Increase log verbosity (`--verbose` → INFO, `--verbose --verbose` → DEBUG). |
| `-v`, `--version` | Print the version and exit. |

Run `antenati -h` for the full, up-to-date list.

### Graphical interface

Launch the GUI with the `antenati-gui` command (or the standalone executable
described above):

![GUI Screenshot](https://raw.githubusercontent.com/gcerretani/antenati/master/docs/gui_screenshot.png)

1. Paste the link to the first page of the archive into the **Archive URL** field
   (e.g. `https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x`).
2. Choose a destination folder.
3. The results are saved into a new subfolder named after the archive, such as
   *archivio-di-stato-di-lucca-stato-civile-napoleonico-viareggio-1807-nati-19944549*.

## AWS WAF challenge

Outside Italy, the Portale Antenati gallery pages are often protected by an AWS
WAF challenge that this tool cannot solve, and the download fails with an *AWS
WAF challenge cannot be bypassed* error (see
[#25](https://github.com/gcerretani/antenati/issues/25)). The IIIF manifest and
the images themselves are **not** behind the WAF, so you can work around it:

1. open the gallery page in your browser;
2. copy the **IIIF manifest** link at the bottom of the left side panel (it
   looks like `https://dam-antenati.cultura.gov.it/antenati/containers/.../manifest`);
3. pass that URL to the tool (both CLI and GUI) instead of the gallery page URL.

## License

Released under the [GNU General Public License v3 or later](https://www.gnu.org/licenses/gpl-3.0.html).
See the [changelog](https://github.com/gcerretani/antenati/blob/master/CHANGELOG.md) for release history.
