# Manual verification (Stage 3)

Hand calculations for the key numbers, so they can be checked without trusting the code.
Every number below is also asserted by the automated tests in `backend/tests/`.

## Cost of one MWh of each thing (Scenario A/B defaults)

| Item | Calculation | $ per MWh |
|---|---|---|
| Gas | fuel 60 + CO2 0.45 t x $50/t = 60 + 22.5 | **82.5** |
| Curtailed renewables | penalty | **10** |
| Battery discharge | wear | **5** |
| Unserved demand | penalty | **1000** |
| Solar / wind used | free | 0 |

## Scenario B, no battery: $10,925

| Period | Demand | Renewables available | Used | Curtailed | Gas | Cost |
|---|---|---|---|---|---|---|
| Morning | 80 | 30 + 20 = 50 | 50 | 0 | 30 | 30 x 82.5 = 2,475 |
| Afternoon | 120 | 120 + 20 = 140 | 120 | **20** | 0 | 20 x 10 = 200 |
| Evening | 150 | 10 + 40 = 50 | 50 | 0 | 100 | 100 x 82.5 = 8,250 |
| **Total** | | | | 20 | **130** | **10,925** |

Check: gas 130 x 60 = 7,800; CO2 130 x 0.45 = 58.5 t x 50 = 2,925; curtailment 200.
7,800 + 2,925 + 200 = **10,925**. Matches CLAUDE.md.

## Scenario B, optimal with battery: $9,175

Battery state of charge (SOC) path: 0 -> **20** -> 0 (store the afternoon surplus, use it in the evening).

| Period | Net load (demand + charge - discharge) | Renewables used | Gas | Battery | Cost |
|---|---|---|---|---|---|
| Morning | 80 | 50 | 30 | idle, SOC 0 | 2,475 |
| Afternoon | 120 + 20 = 140 | 140 | 0 | charge 20, SOC 20 | 0 |
| Evening | 150 - 20 = 130 | 50 | 80 | discharge 20, SOC 0 | 80 x 82.5 + 20 x 5 = 6,700 |
| **Total** | | | **110** | | **9,175** |

Check: gas 110 x 60 = 6,600; CO2 110 x 0.45 = 49.5 t x 50 = 2,475; wear 20 x 5 = 100.
6,600 + 2,475 + 100 = **9,175**. Matches CLAUDE.md.

### Why storing exactly 20 MWh is best (not just "good")

- Each MWh of **afternoon surplus** stored and used in the evening:
  saves 82.5 (gas) + 10 (no curtailment) - 5 (wear) = **+87.5 $**.
  Only 20 MWh of surplus exist, so at most 20 x 87.5 = 1,750 can be saved this way.
  10,925 - 1,750 = **9,175**.
- Each MWh charged **from gas** (any period) and used later costs 82.5 going in, saves 82.5
  coming out, plus 5 wear: **-5 $**. Never worth it.
- Limits not reached: rate 30 MW > 20, capacity 50 MWh > 20. So 20 MWh is the optimum,
  and the LP (Stage 2) independently found the same plan.

## Scenario A: battery is useless, $11,550

No surplus in any period (afternoon: 90 + 20 = 110 < 120), so the only way to fill the battery
is with gas, which loses 5 $/MWh (see above).
Gas: 30 + 10 + 100 = 140 MWh x 82.5 = **11,550**. Path 0 -> 20 -> 0 costs 11,550 + 20 x 5 = 11,650.

## Spot checks of the exact enumerator's ranking (Scenario B)

| SOC path | Hand calculation | Total |
|---|---|---|
| 0, 20, 20 | stores surplus but never uses it: morning 2,475 + afternoon 0 + evening gas 100 = 8,250 | 10,725 |
| 0, 30, 0 (Q18) | afternoon charges 30 but only 20 is surplus, 10 gas = 825; evening gas 70 = 5,775, wear 150 | 9,225 |
| 0, 0, 20 | evening must charge 20 while gas is already at its 100 cap: 20 MWh unserved x 1,000 | 30,925 |
| 0, 40, ... (Q9) | jump of 40 MWh in one hour exceeds the 30 MW rate | infeasible |

These match `python backend\scripts\run_exact.py` exactly.

## Modelling notes surfaced while checking

1. **No end-of-day value for stored energy.** Energy left in the battery after the evening is
   worth $0 (and there is no "must end empty" rule). Paths like 0, 20, 20 are therefore just
   wasteful, not invalid.
2. **Q18 has near-ties.** 0, 30, 0 and 10, 30, 0 cost only $50 more than the optimum. A quantum
   sampler that lands on them is "almost right", which is why Stage 6 reports the approximation
   ratio and not only P(optimal).
3. **All tiers contain the true optimum (20 MWh).** So for these presets the discrete problem
   QAOA solves has the same optimum as the continuous LP (gap $0).
