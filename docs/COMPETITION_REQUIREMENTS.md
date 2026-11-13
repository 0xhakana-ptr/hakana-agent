# TPCTF 2026 authoring requirements distilled

This is an implementation-oriented summary of the local
`CCF-TPCTF赛事规则手册_v2.5.pdf`, the CTFY-0001/CTFY-0002 standards currently
served by the competition site, and the downloaded official challenge package.
The official documents remain authoritative.

## Format

- Track: TPCTF 2026 · 智能体团队赛道.
- Teams are at most four people from the same legal entity.
- The agent track includes authoring. There are three authoring rounds on
  2026-11-21; each team submits at most one themed challenge per round.
- Accepted challenge classes are Web, Pwn and AI Security. AI Security is
  represented in `metadata.yaml` by a supported display category, normally
  `web` or `pwn`, plus an `ai-security` tag.
- The agent must operate without human intervention during the task.

## Package requirements

- `metadata.yaml` must parse and carry `name`, `description`, `difficulty`,
  `tags`, `category`, and questions.
- At least one question must have a per-instance answer. Question modes include
  dynamic, checker and seeded.
- Every dynamic answer must be delivered to the player through a running
  service, a rendered `attachments/*.tpl`, an attachment builder, or a seeder.
- A package with a service needs `docker-compose.yml` and build contexts.
- Every service needs a health check, resource limits, and an allowed Compose
  surface.
- Every non-QA package ships `solution/exploit.py` or `solution/Dockerfile`.
- Every upload ships a non-empty `solution/WRITEUP.md`.
- The reference exploit prints `Q[<question_id>]: <value>`.
- Minted answers must be discovered through the deployed challenge; reading
  `/answers`, `ANSWER_*`, `params/answer.json` or `params/manifest.json` in the
  exploit process is invalid.
- No service may contain a literal `FLAG{...}` or static answer.

## Safety and fairness

A challenge must not:

- attack the platform, worker, LAN, cloud metadata, or another team;
- require public-internet access at runtime;
- depend on a platform-provided model at challenge runtime;
- use hidden communication between authoring and solving;
- rely only on guessing/brute force where a normal public dictionary cannot
  solve it;
- disclose a flag, be a trivial task, or copy a public challenge;
- inject text aimed at the agent that will solve the challenge.

## Review and smoke

For automatic review the platform:

1. charges the team's smoke quota;
2. creates a fresh instance and mints the answers;
3. builds and starts the Compose stack;
4. runs `solution/exploit.py` inside the exploit runner or the supplied
   `solution/Dockerfile`;
5. compares every expected answer with what the exploit printed.

Verdicts:

- `solved`: approve and publish;
- `unsolved`: reject;
- `estate_failed`: reject until the stack is fixed;
- `malformed`: reject until metadata is fixed;
- `errored`: platform-side failure, retried without judging the author.

The competition also performs a model review for content aimed at solver
agents. The challenge may attack its own local model/tools, but cannot address
the external solver agent or reviewer.

## Scoring

The public implementation prices an authored challenge by the fraction of the
author's own division that fully solves all of its priced questions. The
default curve is:

| full-solve rate | authoring multiplier |
|---|---:|
| 0% | 0.20 |
| 5% | 1.00 |
| 5%–25% | 1.00 |
| >25% | falls linearly toward 0.30 at 100% |
| 100% | 0.30 |

The curve is applied per authored challenge and summed. The author's own team
does not count as a solver. The contest's final ranking combines solving and
authoring according to the competition board configuration.

QuestionForge therefore chooses a target near 12% rather than either
"impossible" or "tutorial".

## Round operations

- Use the current round's topic, not a prebuilt answer.
- Keep one coherent challenge rather than averaging unrelated motifs.
- Do not leak the intended technique in the public description or tags.
- Prefer two gated questions over one binary fact.
- Build two independent gates around the final answer.
- Test from fresh state.
- Keep package size and dependencies small.
- Preserve the exact package and verification evidence for later review.
