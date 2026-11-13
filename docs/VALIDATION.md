# Validation record

Validated on 2026-11-13 before the TPCTF authoring window opened.

## Unit tests

```text
Ran 20 tests
OK
```

Covered:

- fact/intent graph persistence;
- JSON extraction in the model transport;
- OpenAI-compatible JSON calls against a local mock server;
- CTFY multipart upload construction;
- all four recipe compilers;
- two dynamic answers and rotator wiring;
- answer-leak/static-flag rejection;
- multilingual topic classification.
- blind HTTP solver tool loop against a live in-process challenge;
- fragment-mode AI memory reconstruction;
- nested object graph authorization behavior.
- conservative behavior when an external target provides only one trial.
- headless Claude Code invocation with tools, persistence and permission bypass disabled.
- automatic Claude Code CLI → direct API fallback.

## Official CTFY checks and smoke matrix

The official `ctfy 0.8.0` authoring checker was run against:

```text
.tmp/final-ai
.tmp/final-web
.tmp/final-object
.tmp/final-pwn
.tmp/final-ai-hard
.tmp/final-web-hard
.tmp/final-pwn-hard
```

All seven returned:

```json
{
  "ok": true,
  "problems": [],
  "audit": {
    "outcome": "ok",
    "errors": 0,
    "warnings": 0,
    "findings": []
  },
  "advisories": []
}
```

## Official local smoke

The official `ctfy authoring smoke --local` path built and started each
package. The public wheel does not ship the prebuilt
`ctfy-exploit-runner` image, so the repository's small QA runner was used; it
installs the same `ctfy.challenge.exploit` contract and executes the reference
solution in an isolated container on the challenge network.

| Variant | Result |
|---|---|
| `ai-tool-agent` default | `OK: captured 2/2 answers` |
| `web-preview-ssrf` default | `OK: captured 2/2 answers` |
| `web-object-graph` default | `OK: captured 2/2 answers` |
| `pwn-stack-chain` default | `OK: captured 2/2 answers` |
| `ai-tool-agent` hardened | `OK: captured 2/2 answers` |
| `web-preview-ssrf` hardened | `OK: captured 2/2 answers` |
| `pwn-stack-chain` hardened | `OK: captured 2/2 answers` |

The exact answer values are intentionally not retained in this document; every
smoke run mints fresh values.

## Agent container

```text
docker build -t questionforge:local .
docker run --rm ... questionforge:local --theme ... --dry-run
{"status": "prepared-offline"}
```

The image runs as a non-root user, contains no credentials, and writes only
under `/ctfy/work`.

Claude Code CLI is installed in the image:

```text
claude --version
2.1.323 (Claude Code)
```

## Blind calibration status

The blind solver transport and tool loop were tested with a scripted local
solver. A full stochastic calibration requires the competition model gateway or
a configured test target, so its measured rate is recorded as `estimate` when
those are unavailable. The agent does not substitute a model estimate for a
false `live` result.

## What still needs competition-time validation

The current public authoring page says the first authoring window opens
2026-11-21 10:00 Beijing time. Until then, the real platform's uploaded-package
dry run and automatic smoke cannot be exercised for this event. The agent is
designed to perform both before spending an upload, and it reports platform
refusals without converting them into a model-generated success claim.
