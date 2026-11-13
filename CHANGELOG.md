# Changelog

## 0.3.0 — 2026-11-13

- Installed Claude Code CLI 2.1.323 in the Agent image.
- Added `auto | claude_cli | direct` model backend selection.
- Claude Code runs headless with `--bare`, `--restricted`, `--tools ""`,
  `--no-session-persistence`, and no permission bypass.
- Added automatic fallback from Claude Code CLI to direct Anthropic/OpenAI
  compatible HTTP.
- Added CLI configuration, diagnostics, tests and architecture documentation.

## 0.2.0 — 2026-11-13

Champion-mode upgrade.

- Added the `web-object-graph` recipe: nested object authorization bypass with a
  public root object, recursive relation expansion and a checkpoint-gated export.
- Increased ideation from three candidates to six and exposed 0/1/2 difficulty
  variants to the planner.
- Added difficulty-sensitive variants:
  - Web broker: hidden vault origin until the asset index is fetched;
  - AI agent: two-fragment memory reconstruction;
  - Pwn relay: master route disclosed only after the first frame.
- Added a blind HTTP solver loop. It receives only the public brief,
  attachments, target endpoint and tool responses; source and answers are
  excluded from its context.
- Added calibration decisions that raise difficulty above 25% solve rate and
  lower it below 5%.
- Added `AUTHORING_CALIBRATION_*` controls and optional platform test-target
  support.
- Expanded verification to 18 tests and seven official CTFY smoke variants.

## 0.1.0 — 2026-11-13

- Initial CTFY package compiler with Web SSRF, AI tool-agent and Pwn stack-chain
  recipes.
- Fact/intent graph, CTFY static checks, smoke runner and direct REST upload.
