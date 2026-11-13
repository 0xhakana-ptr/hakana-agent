# Architecture and design rationale

## 1. What the agent optimises

The platform is not asking for the hardest possible puzzle. Its public authoring
board prices a submission by the fraction of the author's own division that
fully solves it. The curve used by CTFY 0.8.0 has these properties:

- solve rate `0.05` through `0.25` -> multiplier `1.0`;
- rate `0` -> multiplier `0.20`;
- rate `1` -> multiplier `0.30`;
- linear segments outside the peak band.

QuestionForge therefore asks the model for an estimated rate around `0.12`,
rejects public descriptions that disclose the intended vulnerability, and
prefers two gated questions because a challenge counts only when every priced
question is solved.

The second optimisation target is reproducibility. In automatic review a smoke
run must start a fresh instance, execute the reference solution, and match the
answers minted for that instance. A hard idea that the author's own exploit
cannot reproduce is worth zero. The deterministic compiler and smoke gate exist
to protect this.

## 2. Why the LLM does not write files directly

A general coding model can write a good service, but an unrestricted
model-generated tree creates several correlated failures:

- an answer path that is not mounted into the service that reads it;
- YAML or Compose fields the platform refuses;
- a model secret accidentally stored in the package;
- prompt injection aimed at the solver agents;
- a reference exploit that imports tools the runner does not have;
- slight differences between the asset a player downloads and the service they
  connect to.

QuestionForge separates creativity from execution:

1. the model compares several recipes and supplies constrained narrative,
   difficulty-level and parameter data;
2. deterministic code compiles the challenge, compose file, rotator, service,
   attachment builder and reference exploit;
3. deterministic checks reject answer leakage and policy violations;
4. the official checker and a smoke run decide whether the artifact works.

The model is useful for theme fit, naming, target difficulty and adversarial
review. It is not trusted to create shell commands, compose capabilities,
network destinations or answer-handling code.

## 3. Sapper V2 ideas retained

QuestionForge keeps the parts of Sapper V2 that transfer from solving to
authoring:

- **History survives context loss.** Facts and intents are one JSON node per
  file under the run, like Sapper's fact graph.
- **A harness is more portable than one model.** The planner and reviewer can
  run through a tool-disabled headless Claude Code CLI, a direct
  OpenAI/Anthropic-compatible transport, or a configured fallback between them.
- **Evidence beats narration.** A package is not considered built or working
  because the model says so; a file hash, checker result and smoke verdict are
  recorded.
- **Roles have different incentives.** The planner seeks fit; the reviewer is
  instructed to find answer leaks, trivial bypasses and unverifiable paths.
- **Bounded escalation.** The agent does not spend the round generating endless
  ideas. It selects one candidate, compiles it, and spends the remaining time
  on verification.

It deliberately does not copy the pentest-specific tmux worker swarm. A
challenge package has one authoritative artifact; parallel writers would make
the final tree harder to reason about.

## 4. Public agent cases that informed the design

### CTF Agent by Veria Labs

The BSidesSF 2026 agent uses a coordinator plus per-challenge solver swarms and
isolated containers. The useful idea is role separation and isolation, not
running every role in parallel. QuestionForge uses one constrained designer and
one adversarial reviewer; the challenge itself is tested in an isolated
Compose environment.

### D-CIPHER

D-CIPHER separates planning from heterogeneous executors. QuestionForge mirrors
the split as a planner and deterministic recipe compiler. This is especially
important for authoring: an executor may propose a novel design, but only a
small allow-listed tool set can turn it into a platform package.

### Cybench and NYU CTF Bench

These benchmarks make the environment and grading contract executable. The
lesson is that a challenge is not a story plus files; it is a reproducible
state transition with success evidence. Every QuestionForge recipe therefore
ships a machine-checkable reference exploit and a two-stage dynamic-answer
delivery path.

### CyberGym and CyberGym-E2E

CyberGym's strongest design choice is proof by execution: a hypothesis is only
valuable when it produces a verified PoC. QuestionForge applies that principle
to authoring by treating the official smoke as the primary quality signal and
the model review as advice.

## 5. Blind difficulty calibration

An authoring submission is scored only indirectly by how the solving field
behaves. Model self-estimates are therefore treated as a prior, not a result.

The calibration path starts a private local instance with freshly minted flags
and gives a separate solver model only:

- the player-facing description;
- currently visible question prompts;
- public attachments;
- an HTTP tool restricted to the target instance;
- a submit tool whose success boolean is the only answer oracle.

It never receives `services/`, `solution/`, `AUTHORING.md`, the intended path,
`/answers`, or the expected values. Each trial starts from fresh challenge
state. The observed full-solve rate is compared with the scoring plateau:

```text
0/5 solved    -> too hard, lower one difficulty level
1/5 solved    -> 20%, inside the full-credit band
2+/5 solved   -> too easy, raise one difficulty level
```

Five trials are a screening signal, not a statistical guarantee, so the result
is labelled low/medium confidence and recorded beside the estimate. An
adjustment rebuilds the challenge and reruns CTFY validation before it can be
uploaded.

## 6. Execution flow

```text
topic + quota
     |
     v
limited ideation (6 candidates over 4 recipe families)
     |
     v
blueprint validation -> recipe compiler -> package
     |                                      |
     |                                      +-> structural validator
     |                                      +-> ctfy authoring check
     |                                      +-> optional local smoke
     |
     +-> adversarial review
     +-> blind solve x N -> difficulty adjustment -> revalidate
     |
     v
platform dry-run -> upload -> poll automatic review -> report
```

The run stops early on local errors. It uploads only after the pre-upload gate
passes, because each smoke and upload consumes a bounded team quota.

## 7. Failure strategy

- No LLM: classify the theme and use the matching deterministic recipe.
- No platform: still emit a complete package and verification report.
- `ctfy` missing: use structural checks and let the server-side dry run cover
  platform-specific rules.
- Docker unavailable: use platform automatic smoke after upload.
- Model review unavailable: do not invent a verdict; record the failure.
- Calibration target or Docker unavailable: keep the model estimate, mark it as
  estimated/low-confidence, and do not claim a measured pass rate.
- Authoring window closed: retain the package rather than repeatedly uploading.
- Platform errors in a smoke: do not treat them as a challenge defect when the
  platform records `errored`.
