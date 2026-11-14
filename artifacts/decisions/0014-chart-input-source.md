# 0014: Where the chart's run gets its input

- Status: Accepted (2026-11-14)
- Related: [plan 03](../plans/03-part2-helm-chart.md), [REVIEW.md](../../REVIEW.md) #6 and #17

## Context

The chart as received downloads a fixed-date URL (`...snapshot-2026-10-29.zip`) on every run, into a 50Gi PVC. On kind this really worked: a 2.4 GB zip that unpacks to a 13.9 GB `.txt`. But:

- The date never changes, so every later week reloads the same old file, or fails once it's removed.
- Our pipeline holds the parsed records in memory: 214 MB for the 48k-line sample, so tens of GB for the full 16 million. The full snapshot needs the production design in NOTES, not this chart.
- The brief asks that, if the chart is installed, "your pipeline must run and write its output".

## Options

1. Keep the download as the default, and fix the date by working out the latest snapshot name.
2. Default to the sample baked into the image. Keep the download as an opt-in, with the URL and file name as values, into an `emptyDir`.
3. Default to a pre-loaded PVC that someone fills by hand.

## Decision

Option 2.

- `input.path` defaults to `/app/data/persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz`, which is in the image. An install works with no network access and finishes in seconds.
- `input.download.enabled: true` adds an init container. It downloads `input.download.url` with `wget` (which fails on HTTP errors), unzips it into an `emptyDir` at `/input`, deletes the zip, and checks that `input.path` exists. If the check fails, the init container fails and the pipeline never starts.
- `emptyDir`, not a PVC: the input is used once per run, and there's no reason to keep it or pay for a disk between weeks. `input.download.sizeLimit` caps it.

## Consequences

- The default install proves the chart end to end, but always loads the same sample. That's stated in values.yaml and the chart NOTES.
- A weekly real run needs the URL and file name set for each week. Finding the latest snapshot automatically, and handling the full size, belong to the production design (NOTES.md), not this chart.
- The node needs about 16 GB of free scratch space for one full download. `sizeLimit` makes the pod fail cleanly instead of filling the node.
