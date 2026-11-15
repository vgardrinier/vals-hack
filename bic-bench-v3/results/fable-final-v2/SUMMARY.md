# BIC-Bench V3 Pilot Results

## Model comparison

| Model | Mean | Std. dev. | Actionful mean | Pass rate | Blocking violations | No-action failures | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|
| anthropic/claude-fable-5-2 | 59.6% | 7.7% | 84.1% | 33.3% | 0 | 7 | 18.9 min |

## Per-task means

| Task | anthropic/claude-fable-5-2 |
|---|---:|
| redwood-acme-credit-ledger | 0.0% |
| redwood-audit-export-legal-hold | 90.0% |
| redwood-dedicated-slo-credit | 33.3% |
| redwood-model-catalog-launch | 66.7% |
| redwood-nordbank-residency-commitment | 66.7% |
| redwood-northwind-paid-claim | 70.0% |
| redwood-proxima-exception-renewal | 63.3% |
| redwood-smart-routing-fallback | 86.7% |

## Usage

| Model | API calls | Prompt tokens | Cached tokens | Cache writes | Completion tokens | Reported API cost | Estimated list cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| anthropic/claude-fable-5-2 | 381 | 14,568,320 | 13,024,202 | 1,543,250 | 357,736 | $0.0000 | $32.35 |
