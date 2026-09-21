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

## Reporting a vulnerability

Please report security issues privately via a [GitHub security advisory](https://github.com/gcerretani/antenati/security/advisories/new) rather than a public issue. If that's not available to you, open an issue on the [issue tracker](https://github.com/gcerretani/antenati/issues) without including exploit details, and we'll follow up privately.
