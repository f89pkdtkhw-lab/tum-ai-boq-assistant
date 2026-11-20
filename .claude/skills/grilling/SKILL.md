---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
---

<!-- Generiert aus .agents/skills/grilling/SKILL.md mit python tools/agents_sync.py. Hier nicht bearbeiten. -->

In the team kickoff, use the bounded board workflow below instead of the unbounded interview and final confirmation. Outside kickoff, follow the interview rules that follow.

## Kickoff on the team board

Post at most two rounds via `tools/board post -` (stdin), starting with `[<Name> · <Agent>] @f89pkdtkhw-lab Kickoff · Runde <N>`. Number each question, phrase it so “yes” accepts the recommendation, and give a concrete recommendation and reason. End with `Ohne Antwort bis <HH:MM mit Zeitzone>: **Annahme** <Empfehlung>.` The single deadline is ten minutes after kickoff step 3 starts; round 2 never resets it. Read replies with `tools/board unread`; research facts and prepare independent work meanwhile. At the deadline, record unanswered recommendations as **Annahme** in `docs/case.md` and on the board, then proceed without final confirmation. No questions means no wait. Do not invent credentials or mandatory partner data.

## Interview outside kickoff

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent with a fresh context window to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
