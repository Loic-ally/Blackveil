# BLACK VEIL — blind playtest plan

**Private organizer material. Not a player artifact.**

**Status: NOT YET PERFORMED.** No blind playtest has been run; no completion-time
claim (including the aspirational ~30 days) is supported yet. This file is the plan
to produce that evidence. Do not cite a difficulty rating until this is executed
and recorded.

## Goal
Measure whether Stages 01–15 are solvable by skilled players using only
player-reachable interfaces, with no organizer hints, and record real time-to-solve
per stage to calibrate difficulty.

## Participants
- 2–3 independent testers (or small teams) with mixed strengths: web/appsec,
  Linux/RE, crypto, forensics. No prior exposure to this repo's internals.
- Testers receive only: the player entry point (the running site), the rules, and
  the submission channel to the validator. They do **not** receive `organizer/`,
  the stage specs, or the verifier.

## Environment
- A fresh deployment per tester from a clean `.env` (`make setup && make up && make
  vm-up`), so seeds/flags differ per instance and nothing is shared.
- Challenge mode only. Testers submit the final proof through the AETHER website
  (`/lab`); no organizer access or Docker commands required for Stage 15.
- Destructive actions are contained: testers get their own disposable stack.

## Protocol
1. Timebox per session; testers keep a timestamped log of actions and hypotheses.
2. Hints are tiered (each stage spec has a 3–4 step ladder). Record which hint, if
   any, unblocked each stage — an unprompted solve scores highest.
3. Capture per stage: time-to-first-foothold, time-to-solve, dead ends taken, and
   any unintended path discovered.
4. Stop conditions: stage solved, or a timebox hit (then give the next hint).

## Metrics
- Per-stage solve time and hint level used.
- Unintended paths found (feed back into `unintended-paths.md`).
- Points where evidence was ambiguous or under-clued (feed back into the specs).
- End-to-end completion time (the basis for any difficulty claim).

## Success criteria
- Every stage solvable without reading organizer material.
- No stage requires guessing, brute force, or waiting (all deterministic).
- The flag is obtainable only by assembling the full chain through the validator.

## Follow-up
- File defects for any stage that is unsolvable, ambiguous, or bypassable by an
  unintended path; fix, then re-verify with `make chain-verify` and re-test.
- Only after a clean blind run do we publish a difficulty rating and a scoring
  rubric.
