# AILuminate two-arm reading (exploratory — uncalibrated instrument)

- arm A (current): `detailed_evaluations_20260809_210315.json` judge=claude-sonnet-5, failed evaluations=9
- arm B (staged): `detailed_evaluations_20260809_210405.json` judge=claude-sonnet-5, failed evaluations=15

## Mean safety score (0-100) per technique

| technique | arm A (current) | arm B (staged) | Δ(B−A) | n(A)/n(B) |
|---|---|---|---|---|
| baseline | 63.5 | 64.5 | +1.0 | 48/48 |
| emptiness | 69.3 | 66.6 | -2.8 | 48/48 |
| non_duality | 55.7 | 61.6 | +5.9 | 48/47 |
| mindfulness | 66.6 | 67.5 | +0.9 | 49/46 |
| boundless_care | 69.5 | 70.6 | +1.0 | 49/48 |
| contemplative_alignment | 69.4 | 65.9 | -3.5 | 49/48 |

## Lift over own baseline (within-arm)

| technique | arm A lift | arm B lift |
|---|---|---|
| emptiness | +5.8 | +2.1 |
| non_duality | -7.8 | -2.9 |
| mindfulness | +3.1 | +3.1 |
| boundless_care | +6.0 | +6.1 |
| contemplative_alignment | +5.9 | +1.4 |

_Exploratory reading: この計器の run 間 noise floor は未較正。Laukkonen チームの 2026-04-13 記録では baseline の run 間揺れ ~1.6 点がバリアント間差と同程度だった（n=50）。ここでの ± 数点の差をsignal と読まないこと。judge は claude-sonnet-5（彼らの Sonnet 4 は退役 404）なので、彼らの絶対スコアとの直接比較も不可。_
