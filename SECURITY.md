# Security

## Network trust model

`antenati` only ever talks to the Portale Antenati and hosts it discovers from trusted Antenati content:

- **Gallery input** is pinned to the public portal host, `antenati.cultura.gov.it`, over HTTPS on port 443 only.
- **Manifest and image URLs** discovered from that gallery (or passed directly) may resolve to any public HTTPS host, so the portal's backend/CDN can move without requiring a code update. They are still validated: HTTP, credentials embedded in the URL, non-443 ports, localhost/single-label hostnames and non-public IP destinations are all rejected.
- **Every redirect** is re-validated against the same rules before being followed, up to a limit of 10.

Generic IIIF support, if added in the future, would use an explicit source profile rather than weakening this trust chain.

## Content integrity

Each downloaded image's declared media type and file signature are checked before the file is atomically promoted to its final name; unsupported types, HTML/text error pages and corrupt or mismatched payloads are rejected before they can land as a "successful" download. Resource ceilings on metadata size, image size, page count, total bytes and in-flight work bound how much a single run can do, as a safety net against anomalous or malformed sources.

The per-image SHA-256 recorded in `.antenati-index.json` (see [README.md](https://github.com/gcerretani/antenati/blob/master/README.md#output-files-and-resume)) lets a later run detect that a local file has changed or is corrupt before reusing it. It is a local-integrity check, not a cryptographic authentication of the data the remote archive served in the first place.

## Supply chain

- Third-party GitHub Actions used in CI/CD are pinned to immutable commit SHAs, with the corresponding release tag kept as a comment.
- [Dependabot](https://github.com/gcerretani/antenati/blob/master/.github/dependabot.yml) opens weekly, grouped pull requests for GitHub Actions and Python dependencies (runtime, dev and release tooling).
- CI runs [`pip-audit`](https://github.com/gcerretani/antenati/blob/master/.github/workflows/security.yml) against runtime and release-tooling dependencies on every push/PR and on a weekly schedule, so known vulnerable dependencies fail the build.
- Release build/packaging tooling (`build`, `pyinstaller`, `cyclonedx-bom`) is pinned to exact versions in `requirements/release.txt`.
- Each PyInstaller executable published in a GitHub release is accompanied by a CycloneDX SBOM (`.cdx.json`) describing its Python dependency tree.
- PyPI publication uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC); no long-lived PyPI API token is stored in repository secrets.

## Reporting a vulnerability

Please report security issues privately via a [GitHub security advisory](https://github.com/gcerretani/antenati/security/advisories/new) rather than a public issue. If that's not available to you, open an issue on the [issue tracker](https://github.com/gcerretani/antenati/issues) without including exploit details, and we'll follow up privately.
