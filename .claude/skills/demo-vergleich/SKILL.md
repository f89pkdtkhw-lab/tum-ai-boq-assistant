---
name: demo-vergleich
description: Compare the current hackathon solution and a traceable baseline on the same examples, making improvements and regressions visible for the pitch.
---

<!-- Generated from .agents/skills/demo-vergleich/SKILL.md using python tools/agents_sync.py. Do not edit here. -->

Read the case brief and acceptance examples. First clarify which user decision matters. The baseline can be the partner's current workflow or a simple, plausible domain rule. Document which you actually use.

**One run:** QA fixes inputs, expected results and metric before execution. Where possible include an everyday case, a difficult case and incomplete input. Run both variants under identical conditions. Reuse the same cases after the next change. An additional unused partner example can serve as a final check.

For discrete results, this helper compares two observed outputs against expectations. It reads a UTF-8 JSON file containing a list of cases. Format example (existing JSON keys remain unchanged):

```json
[{"fall":"Group of five people","soll":"room:isar","bisher":"room:isar","prototyp":"room:isar"}]
```

```sh
python .agents/skills/demo-vergleich/scripts/vergleich.py ergebnisse.json
```

`null` for a variant means an executed attempt returned no result. If the run itself is missing, mark it separately as pending. For time, cost or simulation metrics, use the original unit and identical inputs for both variants.

Record inputs, metric, comparison method, commit and result in the issue. Report successes with denominators, new successes and regressions. If a new attempt offers no benefit, keep the more demonstrable revision. Use only reproduced numbers in the pitch. With few examples, limit claims to those exact cases.
