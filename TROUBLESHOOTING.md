# Troubleshooting

This document covers error and limit conditions you may hit while using `antenati`. For installation and everyday usage, see [README.md](https://github.com/gcerretani/antenati/blob/master/README.md).

## The gallery URL fails with HTTP 403 or a WAF challenge

The public gallery HTML can be blocked for automated clients by the portal's AWS WAF, even while the direct manifest and IIIF image backends remain reachable. You'll see an error such as:

> AWS WAF challenge cannot be bypassed. Workaround: open the gallery page in a browser, copy the "IIIF manifest" link at the bottom of the left panel and pass that URL to this tool instead.

To work around it:

1. open the gallery in a browser;
2. copy its **IIIF manifest** link from the portal interface;
3. pass that manifest URL directly to `antenati` or the desktop app instead of the gallery URL.

See [issue #25](https://github.com/gcerretani/antenati/issues/25) for background. The project's scheduled live checks test gallery HTML, direct manifest access and image download as three separate canaries, precisely so a frontend/WAF failure doesn't hide backend status.

## The download finished as "Download incomplete"

At the end of a run, `antenati` always prints one summary panel: **Download complete**, **Download cancelled**, or **Download incomplete**, followed by counts for Downloaded, Reused, Failed and bytes Written, and — if anything failed — a **Failures** section listing each failed page and the reason.

A partial run still writes its provenance files, so re-running the same command with `--existing resume` picks up exactly where it stopped instead of redownloading everything.

## It says the destination already contains files

With the default `ask` policy, a non-empty destination triggers a choice between:

- `resume` — verify and reuse valid downloads (recommended);
- `overwrite` — download again and replace planned files;
- `skip` — reuse verified files, refuse ambiguous existing ones;
- `cancel` — stop without changing the directory.

For scripts or `--format json` runs, `ask` cannot prompt interactively — pass an explicit policy such as `--existing resume` or `--existing error` up front.

## The images are smaller than I expected

`-s 0` (the default) requests the source's native resolution; any other `-s N` bounds the longest side to `N` pixels.

The portal itself restricts full-resolution requests at the server: its WAF rejects a literal `full`/`max` size token as an anti-bulk-download filter, and its image server additionally caps the pixel area of any request that isn't a same-size no-op. `antenati` already requests native resolution in the one way that satisfies both restrictions, so there's nothing to configure — but both restrictions are the portal's own policy and could change independently of this tool.

## The download stopped with a resource-limit message

`antenati` enforces fixed safety ceilings meant to protect against anomalous or malformed sources, not to cap what a normal register needs:

- up to 20,000 canvases (pages) per manifest;
- up to 20 MiB of manifest/metadata;
- up to 512 MiB per image;
- up to 20 GiB of images per run.

These limits are **not configurable** from the CLI or the desktop app. If you hit one on a legitimate register, please [open an issue](https://github.com/gcerretani/antenati/issues).

## Cancelling takes a few seconds

Cancelling (Ctrl-C on the CLI, the **Cancel** button in the desktop app) stops any work that hasn't started yet immediately. A page whose download is already in flight stops at the next chunk it receives; in the rare case where a connection is completely stalled, it's bounded by the HTTP connect/read timeouts (10 s / 60 s) rather than being killed instantly.

## It worked before and now it doesn't

The Portale Antenati is a third-party service and may change its HTML, metadata or IIIF structures without notice. The offline test suite verifies the structures this project currently supports; it can't guarantee future portal compatibility. If something that used to work has stopped, please [open an issue](https://github.com/gcerretani/antenati/issues) with the URL and the error you got.
