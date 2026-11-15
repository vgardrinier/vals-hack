# Restricted-egress harnesses

BIC-Bench tasks set `allow_internet = false`. The stock Claude Code and Codex harnesses therefore cannot reach their model APIs. Two team-local aliases preserve the offline task environment while allowing only the model transport endpoint:

| Alias | Runtime egress allowlist | Web tools |
| --- | --- | --- |
| `claude-code-bic-v1.0.0` | `api.anthropic.com` | `WebSearch` and `WebFetch` removed |
| `codex-bic-v1.0.0` | `api.openai.com` | No additional Web endpoint allowed |
| `mini-swe-bic-v2.4.6-lf` | `api.anthropic.com`, `api.openai.com` | No browser or Web tools |

The aliases are derived from the installed Vals harnesses. No benchmark answer, context, or scoring rule is added to either harness. Package installation happens in Valkyrie's separate install phase; evaluated task runtime egress remains restricted to the listed API domain.

This distinction is important: the model API must remain reachable for inference, but the agent cannot browse public websites or retrieve outside information while solving a task.

`mini-swe-bic-v2.4.6-lf` is the primary controlled-comparison harness. It uses
the pinned upstream mini-SWE-agent v2.4.6 code and one contract for both model
providers. The local package also forces shell scripts to LF endings so the
same archive installs correctly in Valkyrie's Linux sandboxes.
