Simulated shifts: **200** · worker-shifts: **1600** · critical events (true core temp reached limit): **485** · actionable window: 60 min · ECTemp core-temp error vs. truth: **0.24 °C RMSE**

| System | Detected | Median lead (min) | Mean lead (min) | Missed | False alarms / 100 worker-shifts | Alarm precision | Workers never in danger who were alarmed |
|---|---|---|---|---|---|---|---|
| Redline v2 (Warning or higher) | 456 (94%) | 50 | 39.2 | 29 | 51.6 | 35% | 15% |
| Redline v2 (Advisory or higher) | 484 (100%) | 60 | 50.1 | 1 | 173.0 | 12% | 42% |
| Redline v1, trend only (Warning or higher) | 319 (66%) | 52 | 38.9 | 166 | 48.9 | 32% | 15% |
| Naive WBGT alarm (≥ 28.2 °C) | 402 (83%) | 60 | 53.2 | 83 | 281.1 | 6% | 100% |
| Naive heart-rate alarm (> 180 − age, sustained) | 91 (19%) | 57 | 42.9 | 394 | 66.5 | 10% | 15% |
