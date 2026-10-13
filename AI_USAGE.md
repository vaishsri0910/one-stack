# AI_USAGE

**Tool:** Claude (Claude Code, model Claude Sonnet 5.5).

**What the AI did:** Nearly everything in this repo was written by the AI in a
single session at my request ("get this project done"): reading the assignment
PDF, identifying the rule conflicts, writing DECISIONS.md, the engine, the tests
(rule tests, reference model, model-based test, stress test), the docs, and
running the tests.

**What I verified / how:** The AI ran the test suite, and mutation-checked the
tests by temporarily breaking the engine (removing seat locks, removing the user
lock, unsorted lock order, allowing late confirm after retake). Its first version of
the cap test did *not* catch the removed user lock; that test was strengthened
until it did.

**Honest limits:**
- I (the human submitter) did not write this code line by line; before any
  follow-up discussion I need to read and be able to explain it. The decisions in
  DECISIONS.md are the AI's proposals; review them and change what you disagree with.
- The commit history was produced in one sitting, not spread over a 60-minute
  window, and timestamps were not altered.
