# Threat model

## Trust boundaries

1. **Round theme**: controlled by the organiser but still treated as untrusted
   text. It can influence creativity, not instructions or code.
2. **Model response**: untrusted structured data. Only known recipe IDs,
   sanitised scalar fields, two fixed question IDs and bounded difficulty
   estimates are accepted.
   Claude Code runs in headless `--bare --restricted` mode with every tool
   disabled and no session persistence, so model output cannot directly mutate
   files or execute shell commands.
3. **Generated challenge**: intentionally vulnerable to the player, but must
   not harm the host, platform, node, cloud metadata, other teams, or a public
   service.
4. **Reference exploit**: trusted test code but confined by the CTFY runner.
   It may only use the supplied target and sibling-service addresses.
5. **Platform API response**: evidence from the authoritative platform. Review
   status and smoke verdict are recorded verbatim; model narration cannot
   override them.

## Explicit prohibitions

- no host networking, privileged containers, Docker socket, devices, or
  host-control paths;
- no public runtime egress;
- no answer literal under `services/`;
- no reference exploit reading `/answers`, `ANSWER_*` or `params/answer.json`;
- no text that directs the future solving agent to stop, leak prompts, run host
  commands or submit a fixed value;
- no dependency on a platform-provided LLM at challenge runtime;
- no attacks against the CTFY platform or its scoring infrastructure.

## Intended vulnerable components

The generated challenges are deliberately exploitable:

- `web-preview-ssrf` contains an authority/parser mismatch and an internal vault;
- `ai-tool-agent` contains a trust-boundary error between retrieved context and
  tool-call parsing;
- `pwn-stack-chain` contains stack overflows in a small local binary.

These defects live inside the challenge's own containers and are only reachable
from the challenge entry point supplied by the platform.

## Prompt-injection containment

The ideation and review prompts fence every external text block with labels and
tell the model that the content is data. Generated challenge descriptions are
checked for direct vulnerability disclosure. The AI-security recipe attacks the
challenge's own deterministic assistant; its malicious action strings are built
at runtime by the reference exploit rather than shipped as prose for the solver.
