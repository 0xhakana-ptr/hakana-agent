# Blind difficulty calibration

The scoring curve rewards a solve rate between 5% and 25%. A model's estimate
of that rate is useful for candidate selection but is not evidence. The
calibrator turns the estimate into a measured trial when the runtime supports
it.

## Modes

### `live`

A Docker-capable host, or a platform-provided test target, is available. The
calibrator starts a fresh Web challenge, mints new answers, and runs independent
solver conversations. An external target is treated as one conservative trial
unless the platform supplies an explicit reset mechanism, because its state
cannot be assumed fresh between attempts.

### `estimate`

No Docker/test target or no model gateway is available. The agent records the
blueprint estimate but explicitly labels it low-confidence. It never presents
that number as a measured solve rate.

### `disabled`

Set `AUTHORING_CALIBRATION=0`.

## What the blind solver sees

Only:

- `metadata.yaml` description text;
- the currently visible question prompts;
- files under `attachments/`;
- the challenge target URL;
- HTTP tool observations.

It does not see:

- `services/`, `solution/`, `AUTHORING.md`, `BUILD_MANIFEST.json`;
- the intended solve path;
- `/answers`, `ANSWER_*`, `params/answer.json`;
- expected answer values;
- any filesystem path outside the challenge service.

The solver can only issue absolute paths against the target URL. It may submit
candidate answers; a boolean acceptance response is the only oracle.

## Decision

```text
measured solve rate > 0.25 -> difficulty + 1
measured solve rate < 0.05 -> difficulty - 1
otherwise                  -> keep
```

Difficulty is bounded to levels 0–2. Any adjustment rebuilds the package and
reruns the CTFY authoring check before upload. If local smoke is enabled, it is
rerun too.

## Environment

```text
AUTHORING_CALIBRATION=1
AUTHORING_CALIBRATION_TRIALS=5
AUTHORING_CALIBRATION_TURNS=16

# Optional platform-provided target. Expected values stay local and are never
# included in solver prompts.
AUTHORING_CALIBRATION_TARGET=https://target.example
AUTHORING_CALIBRATION_ANSWERS={"checkpoint":"FLAG{...}","master_key":"FLAG{...}"}
```

Five trials are a screening signal, not a statistical proof. The result is
recorded with low/medium confidence and is always subordinate to official smoke
and the author's review. Fewer than three completed trials never trigger an
automatic level change.
