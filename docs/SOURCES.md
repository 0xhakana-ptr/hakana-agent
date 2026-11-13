# Primary sources reviewed

Accessed 2026-11-13.

## Competition and platform

- TPCTF 2026 competition page and rules:
  `https://ctfy.tsinghua.edu.cn/competitions/c0d8b4e3dd3b42c095d63d7dfa66431f/rules`
- CTFY-0001 agent protocol:
  `https://ctfy.tsinghua.edu.cn/docs/standards/CTFY-0001`
- CTFY-0002 challenge package v2:
  `https://ctfy.tsinghua.edu.cn/docs/standards/CTFY-0002`
- Official downloaded Web/Python-Flask template from the competition authoring
  page, revision v2, observed 2026-11-13.
- Public `ctfy` 0.8.0 package, used to inspect the exact server-side authoring,
  automatic-review and authoring scoring contracts.

Critical implementation facts taken from these sources:

- one challenge upload must mint at least one answer per instance;
- answers must be delivered by a running service, template, builder or seeder;
- the reference exploit prints `Q[<question_id>]: <value>`;
- the solution cannot read `/answers`, `ANSWER_*` or `params/answer.json`;
- automatic review approves a `solved` smoke, rejects a fixed/duplicate or
  unsolved package, and holds incomplete or malicious packages;
- model review rejects text that attempts to steer the solver agent;
- authoring full solve rate `0.05`–`0.25` receives multiplier `1.0`.

## Sapper V2

- Repository: `https://github.com/N1nEmAn/sapper-v2`
- Design notes read: `README.zh-CN.md`, `SKILL.md`,
  `docker/commander/SPEC.md`, `docker/commander/SKILL.md`.

Transferred ideas: durable fact graph, role separation, evidence-backed facts,
bounded autonomy, context handoff and deterministic watchdog-like gates.

## CTF agent examples

- CTF Agent, Veria Labs:
  `https://github.com/verialabs/ctf-agent`
  - coordinator plus isolated solver swarms;
  - cross-solver findings and bounded per-challenge workers.
- NYU CTF Bench:
  `https://github.com/NYU-LLM-CTF/NYU_CTF_Bench`
  - executable benchmark environments and category distribution.
- Cybench:
  `https://github.com/andyzorigin/cybench`
  - task-level environment, iteration limits and graded run logs.
- D-CIPHER paper:
  `https://arxiv.org/abs/2502.10931`
  - planner/executor separation and heterogeneous executor roles.
- CTFusion paper:
  `https://arxiv.org/abs/2605.11504`
  - contamination-aware CTF benchmark construction.
- STRIATUM-CTF paper:
  `https://arxiv.org/abs/2603.22577`
  - protocol-driven state across long CTF trajectories.

## Execution-grounded security agents

- CyberGym:
  `https://arxiv.org/abs/2506.02548`
  - a hypothesis matters when its PoC executes and reproduces the vulnerability.
- CyberGym-E2E:
  `https://arxiv.org/abs/2606.04460`
  - automated environment construction across vulnerability discovery, PoC and
    patch.
- "Autonomous LLM Agents & CTFs: A Second Look":
  `https://arxiv.org/abs/2605.21497`
  - warns against reading benchmark wins as pure reasoning wins and motivates
    explicit architecture comparisons.
- "How Much Does the Harness Matter, and for Whom?":
  `https://arxiv.org/abs/2610.28802`
  - harness/context engineering can materially change yield; model and task
    must be measured rather than assumed.

These are design references, not copied code.
