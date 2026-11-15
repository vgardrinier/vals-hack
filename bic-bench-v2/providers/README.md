# Provider command adapters

Both adapters read one harness or judge request from stdin and write one normalized JSON response to stdout.

## Anthropic

Authenticated Claude run (8 cases, 3 trials, concurrency capped at 5):

```powershell
python bic-bench-v2/run_eval.py `
  --case v2-meridian-results-outreach `
  --case v2-cloudnest-residency-close `
  --case v2-ledgeroak-revenue-posting `
  --case v2-northspan-crane-lift `
  --case v2-payrail-descriptor `
  --case v2-robotex-scanner-config `
  --case v2-earthledger-carbon-report `
  --case v2-lighthouse-quote-correction `
  --trials 3 --concurrency 5 `
  --agent command `
  --agent-command "python bic-bench-v2/providers/anthropic_command.py" `
  --agent-name claude-opus-5-5 --agent-mode tool `
  --judge command `
  --judge-command "python bic-bench-v2/providers/anthropic_command.py" `
  --judge-name claude-opus-5-5 `
  --run-id claude-opus-5-5-pilot-8x3-final-v2
```

Authenticate once with `ant auth login`, then run:

```powershell
python bic-bench-v2/run_eval.py --agent command --agent-command "python bic-bench-v2/providers/anthropic_command.py" --agent-name claude-opus-5-5 --agent-mode tool --judge command --judge-command "python bic-bench-v2/providers/anthropic_command.py" --judge-name claude-opus-5-5 --case <case-id> --trials 3
```

Optional environment variables: `BIC_ANTHROPIC_AGENT_MODEL`, `BIC_ANTHROPIC_JUDGE_MODEL`, `BIC_ANTHROPIC_EFFORT`, and `BIC_ANTHROPIC_TIMEOUT`.

## OpenAI

Set `OPENAI_API_KEY`, then replace the adapter path with `providers/openai_command.py`. Optional variables are `BIC_OPENAI_AGENT_MODEL`, `BIC_OPENAI_JUDGE_MODEL`, `BIC_OPENAI_REASONING_EFFORT`, and `BIC_OPENAI_TIMEOUT`.

Provider credentials are never written to run artifacts. Token usage, request IDs, API latency, model IDs, and estimated cost are retained for reproducibility.
