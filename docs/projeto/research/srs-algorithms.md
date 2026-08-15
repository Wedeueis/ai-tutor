# FSRS or SM-2 — and what state does it require?

Research for [issue #6](https://github.com/Wedeueis/ai-tutor/issues/6) (map: [#1](https://github.com/Wedeueis/ai-tutor/issues/1)).
Date: 2026-08-15. Branch: `research/srs-algorithms`.

**Sourcing rule applied:** every factual claim below is traced to a primary source — SuperMemo's own SM-2 page and its reference Delphi implementation, the `open-spaced-repetition` org's source code and wikis, the Anki manual/FAQ, and the `fsrs` PyPI wheel (v6.3.2) inspected directly. No secondary blog posts are cited for any load-bearing claim.

---

## TL;DR

- The PRD's `SRSMetadata(interval, repetitions, ease_factor, due_date)` + 1–4 rating is **SM-2's state with FSRS's grade scale** — a hybrid that is neither algorithm. SM-2 is natively 0–5; FSRS never stores `ease_factor` or `repetitions`.
- FSRS's per-card state is **two floats** (`stability`, `difficulty`) plus bookkeeping (`due`, `last_review`, `state`, `step`). Retrievability is **derived, never stored**.
- FSRS with **default (unfitted) parameters already beats SM-2**, per the FSRS project's own tutorial; fitting needs on the order of **hundreds to ~1000+ reviews** to pay off, and py-fsrs's optimizer silently returns the defaults below **512 reviews**.
- `py-fsrs` is **MIT**, core install depends only on `typing-extensions` (the optimizer is an optional `torch` extra). Reimplementing the FSRS-6 *scheduler* math in a pure domain layer is ~150 lines and realistic. Reimplementing the *optimizer* is not.
- SM-2 → FSRS migration is **not a cheap field rename and not a rewrite either**: it is cheap *only if you have kept an append-only review log*. FSRS ships a first-class `memory_state_from_sm2(ease_factor, interval, sm2_retention)` bridge for the case where you have not.
- **Recommendation: implement FSRS-6 directly in the domain layer, with a review log from day one.** Trade-off spelled out at the end.

---

## 1. Exact state and scheduling signature

### 1.1 SM-2

SuperMemo's own description of Algorithm SM-2 ([super-memory.com/english/ol/sm2.htm](https://super-memory.com/english/ol/sm2.htm)) specifies:

> "Split the knowledge into smallest possible items. With all items associate an E-Factor equal to 2.5."

> `I(1):=1, I(2):=6, for n>2: I(n):=I(n-1)*EF`

> `EF':=EF+(0.1-(5-q)*(0.08+(5-q)*0.02))` … "If EF is less than 1.3 then let EF be 1.3."

> "If the quality response was lower than 3 then start repetitions for the item from the beginning without changing the E-Factor (i.e. use intervals I(1), I(2) etc. as if the item was memorized anew)."

Grade scale, verbatim from the same page — **0–5, six values**:

| q | meaning |
|---|---|
| 5 | perfect response |
| 4 | correct response after a hesitation |
| 3 | correct response recalled with serious difficulty |
| 2 | incorrect response; where the correct one seemed easy to recall |
| 1 | incorrect response; the correct one remembered |
| 0 | complete blackout |

**The authoritative state shape** is not prose — it is SuperMemo's own reference plug-in source ([super-memory.com/english/ol/sm2source.htm](https://super-memory.com/english/ol/sm2source.htm)), which declares the entire per-item record as three fields:

```pascal
type TDataRecord=record
       Interval:longint;
       Repetition:byte;
       EF:real;
     end;
```

and the scheduling function as:

```pascal
procedure Repetition(ElementNo,Grade:longint; var NextInterval:longint; commit:WordBool);
```

So SM-2's per-item state is exactly **`(interval, repetition, ease_factor)`**, plus a `due_date` that the host application derives as `last_review + interval`. The PRD's `SRSMetadata(interval, repetitions, ease_factor, due_date)` is therefore a **faithful SM-2 state shape** — the PRD is right about the fields and wrong about calling the algorithm "FSRS/SM-2".

**Two discrepancies worth knowing before implementing**, both visible in the reference source above:

1. The prose says a failure leaves EF unchanged; the reference code applies the EF update **unconditionally**, outside the `if Grade>=3` branch. Pick one deliberately and test it — most third-party "SM-2" implementations differ here.
2. The prose says failure restarts at `I(1)`; the reference code sets `Repetition:=0; Interval:=1`.

**Grade mismatch with the PRD:** SM-2 needs a 0–5 grade, because `EF'` is a quadratic in `q`. The PRD's 1–4 buttons are FSRS's scale. Feeding 1–4 into the SM-2 EF formula is not SM-2 — it silently rescales the whole easiness dynamic (`q=4` becomes "correct after hesitation" and `q=1` becomes "incorrect but remembered", so a "Fácil" press would *decrease* EF). Any SM-2 implementation here needs an explicit, documented 1–4 → 0–5 mapping, which is an invention, not a spec.

**No license text.** Neither SuperMemo page carries a copyright/permission notice about reusing the algorithm; the algorithm description is published openly and is universally reimplemented, but there is no explicit grant to point at. (Anki's own SM-2 implementation is under **AGPL-3.0** — see `ankitects/anki` `LICENSE`: "Anki is licensed under the GNU Affero General Public License, version 3 or later" — so copying Anki's code is not an option for a differently-licensed project.)

### 1.2 FSRS (FSRS-6)

Primary source: the `fsrs` PyPI wheel **v6.3.2**, source inspected directly (`fsrs/card.py`, `fsrs/scheduler.py`), cross-checked against the [awesome-fsrs wiki "The Algorithm"](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm).

**Per-card state — the whole of it** (`fsrs/card.py`, `CardDict`):

```python
card_id: int
state: int            # State.Learning=1 | Review=2 | Relearning=3
step: int | None      # index into learning_steps/relearning_steps; None in Review
stability: float | None
difficulty: float | None
due: str              # datetime
last_review: str | None
```

So: **stability (float) + difficulty (float in [1,10]) + due + last_review + a small learning-step state machine.** There is no `ease_factor`, no `repetitions`, no `interval` — the interval is *recomputed* from stability every time.

**Retrievability is derived, not stored** (`Scheduler.get_card_retrievability`):

```python
elapsed_days = max(0, (current_datetime - card.last_review).days)
return (1 + self._FACTOR * elapsed_days / card.stability) ** self._DECAY
```

with `self._DECAY = -parameters[20]` and `self._FACTOR = 0.9 ** (1 / self._DECAY) - 1`. This is the FSRS-6 power forgetting curve; `_FACTOR` is exactly the constant that forces `R(t=S) = 0.9`.

**Parameter vector: 21 floats** (`DEFAULT_PARAMETERS` in `fsrs/scheduler.py`, matching the wiki):

```
0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722,
0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425,
0.0912, 0.0658, 0.1542
```

Each has a documented lower/upper bound (`LOWER_BOUNDS_PARAMETERS` / `UPPER_BOUNDS_PARAMETERS`), which is what makes the parameter vector safely user-editable.

**Grade scale: 1–4** (`fsrs/rating.py`) — `Again=1, Hard=2, Good=3, Easy=4`. This is the scale the PRD already assumes.

**The core update functions**, verbatim from `fsrs/scheduler.py`:

```python
def _initial_stability(self, *, rating):        # w[0..3] indexed by rating
    return clamp(self.parameters[rating - 1])

def _initial_difficulty(self, *, rating, clamp):
    return self.parameters[4] - (math.e ** (self.parameters[5] * (rating - 1))) + 1

def _next_interval(self, *, stability):
    next_interval = (stability / self._FACTOR) * ((self.desired_retention ** (1 / self._DECAY)) - 1)
    return min(max(round(next_interval), 1), self.maximum_interval)

def _next_difficulty(self, *, difficulty, rating):
    # linear damping + mean reversion toward initial_difficulty(Easy)
    arg_1 = self._initial_difficulty(rating=Rating.Easy, clamp=False)
    delta_difficulty = -(self.parameters[6] * (rating - 3))
    arg_2 = difficulty + (10.0 - difficulty) * delta_difficulty / 9.0
    return clamp(self.parameters[7] * arg_1 + (1 - self.parameters[7]) * arg_2)

def _next_recall_stability(self, *, difficulty, stability, retrievability, rating):
    hard_penalty = self.parameters[15] if rating == Rating.Hard else 1
    easy_bonus   = self.parameters[16] if rating == Rating.Easy else 1
    return stability * (1
        + (math.e ** self.parameters[8]) * (11 - difficulty)
        * (stability ** -self.parameters[9])
        * ((math.e ** ((1 - retrievability) * self.parameters[10])) - 1)
        * hard_penalty * easy_bonus)

def _next_forget_stability(self, *, difficulty, stability, retrievability):
    long_term = (self.parameters[11] * (difficulty ** -self.parameters[12])
                 * (((stability + 1) ** self.parameters[13]) - 1)
                 * (math.e ** ((1 - retrievability) * self.parameters[14])))
    short_term = stability / (math.e ** (self.parameters[17] * self.parameters[18]))
    return min(long_term, short_term)

def _short_term_stability(self, *, stability, rating):   # same-day reviews
    inc = (math.e ** (self.parameters[17] * (rating - 3 + self.parameters[18]))) \
          * (stability ** -self.parameters[19])
    if rating in (Hard, Good, Easy): inc = max(inc, 1.0)
    return clamp(stability * inc)
```

Bounds: `MIN_DIFFICULTY = 1.0`, `MAX_DIFFICULTY = 10.0`, `STABILITY_MIN = 0.001`.

**The actual scheduling signature** (`fsrs/scheduler.py`):

```python
def review_card(self, card: Card, rating: Rating,
                review_datetime: datetime | None = None,
                review_duration: int | None = None) -> tuple[Card, ReviewLog]
```

Scheduler-level configuration lives outside the card: `parameters` (21 floats), `desired_retention=0.9`, `learning_steps=(1min, 10min)`, `relearning_steps=(10min,)`, `maximum_interval=36500`, `enable_fuzzing=True`.

### 1.3 Consequences for the target signature

The PRD wants `calculate_next_review(current_srs: SRSMetadata, rating: int) -> SRSMetadata`. Two facts change that signature:

1. **FSRS needs the review timestamp.** Stability update depends on retrievability, which depends on `now - last_review`. Reviewing a card 2 days late and 20 days late give different results — that is the entire point of the model. The signature must be `calculate_next_review(state, rating, reviewed_at) -> state`, with `reviewed_at` injected as a value, **not** read from a clock. That keeps it a pure function and unit-testable with no I/O mock, which is exactly the constraint in the map. (SM-2 does not need this — it implicitly assumes you review on the due date, which is also one of its known weaknesses.)
2. **FSRS is non-deterministic by default.** `enable_fuzzing=True` calls `random()` to jitter intervals (`FUZZ_RANGES` in `scheduler.py`) to avoid review pile-ups. For a deterministic domain function, set fuzzing off, or make the fuzz an injected strategy. Determinism is available; it is just not the default.

A domain-honest FSRS state is therefore:

```python
@dataclass(frozen=True)
class SRSState:
    stability: float | None      # None = never reviewed
    difficulty: float | None
    due: datetime
    last_review: datetime | None
    phase: Literal["learning", "review", "relearning"]
    step: int | None
```

---

## 2. Does FSRS's advantage depend on fitted parameters?

**Short answer: no for "beats SM-2", yes for "beats itself".**

The FSRS project's own tutorial ([`fsrs4anki/docs/tutorial.md`](https://github.com/open-spaced-repetition/fsrs4anki/blob/main/docs/tutorial.md)) is explicit about what to do before you have history:

> "use the default parameters that are already entered into the 'FSRS parameters' field. Even with the default parameters, FSRS is better than the default Anki algorithm (SM-2)."

**Hard numbers on how much fitting buys you**, from the org's own [srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark) README (10,000 Anki users, ~727M reviews; ~349.9M reviews used for evaluation without same-day reviews):

| Algorithm | Params | Log Loss ↓ | RMSE(bins) ↓ | AUC ↑ |
|---|---|---|---|---|
| FSRS-7 (fitted) | 35 | 0.3437 | 0.0655 | 0.7069 |
| FSRS-6 (fitted) | 21 | 0.3460 | 0.0653 | 0.7034 |
| **FSRS-7 default param.** | **0** | **0.3629** | **0.0910** | **0.6944** |
| FSRS-5 (fitted) | 19 | 0.3560 | 0.0741 | 0.7011 |
| FSRS v4 (fitted) | 17 | 0.3726 | 0.0838 | 0.6853 |
| DASH | 9 | 0.3682 | 0.0836 | 0.6312 |
| HLR | 3 | 0.4694 | 0.1275 | 0.6369 |

Read this carefully: **unfitted FSRS (0 parameters trained) is roughly as good as fitted FSRS v4** — the version Anki originally shipped — and beats DASH, HLR and ACT-R outright. Fitting improves RMSE(bins) from 0.0910 to ~0.065, i.e. it is a real but second-order gain.

*Caveat on this table:* SM-2 is not in the current headline benchmark tables (the benchmark supports `--algo SM2` per the README's CLI section, but the published tables no longer list it). The "FSRS beats SM-2 even with defaults" claim above is the FSRS project's own statement in its tutorial, not something I could verify against a published SM-2 row.

**How much history is "enough":**

- **Historical hard requirements**, from the same tutorial: "In Anki 24.04, at least 400 reviews are required; in older versions, at least 1000 reviews are required." Current: "In Anki 24.06+, there is no minimum number of reviews required for optimization. Based on the number of reviews available, Anki will decide which parameters to optimize." The Anki FAQ confirms: "In Anki 24.06.3 (and newer versions), the optimizer can be used with any number of reviews." ([faqs.ankiweb.net](https://faqs.ankiweb.net/frequently-asked-questions-about-fsrs.html))
- **The Anki manual's** stated failure mode for FSRS is: "Low number of reviews (less than a few hundred). As a machine learning algorithm, FSRS needs data to learn from." ([docs.ankiweb.net/deck-options.html](https://docs.ankiweb.net/deck-options.html))
- **`py-fsrs` itself hard-codes the threshold.** In `fsrs/optimizer.py`, `mini_batch_size = 512`, and:

  ```python
  num_reviews = _num_reviews()
  if num_reviews < mini_batch_size:
      return list(DEFAULT_PARAMETERS)
  ```

  Below 512 reviews the optimizer **returns the defaults unchanged** — it does not even try. Separately, `compute_optimal_retention` raises: "Not enough ReviewLog's: at least 512 ReviewLog objects are required to compute optimal retention".
- **Re-optimization cadence**, from the tutorial: "Once per month should be more than enough. A more sophisticated rule is to optimize after every 2^n reviews: after 512, then after 1024, then after 2048, etc." The Anki manual agrees: "There is no need to optimize your parameters frequently: once every month is sufficient."

**For a single-learner local system this is the decisive finding.** One learner will take months to accumulate 512 reviews and possibly a year to reach the "3000+ reviews" comfort zone. The realistic plan is: **ship with `DEFAULT_PARAMETERS`, never fit, and treat the 21-float vector as configuration.** Optional later: expose a `pipeline srs optimize` command that installs `fsrs[optimizer]` (torch) as a dev-time-only tool once the review log is large enough — the optimizer never needs to be in the runtime path.

---

## 3. Licensing and "can it live in a pure domain layer?"

| Implementation | License | Runtime deps | Notes |
|---|---|---|---|
| [`py-fsrs`](https://github.com/open-spaced-repetition/py-fsrs) (`fsrs` on PyPI, v6.3.2) | **MIT** ("Copyright (c) 2022 Open Spaced Repetition", verified in the wheel's `dist-info/licenses/LICENSE`) | **`typing-extensions` only**; `torch/numpy/pandas/tqdm` are behind the optional `[optimizer]` extra | `Requires-Python: >=3.10` |
| [`fsrs-rs`](https://github.com/open-spaced-repetition/fsrs-rs) | BSD-3-Clause | Rust | Reference impl used by Anki; source of the migration helpers |
| [`fsrs-rs-python`](https://github.com/open-spaced-repetition/fsrs-rs-python) | **none declared** — no `LICENSE` file at repo root, no `license` field in `Cargo.toml`/`pyproject.toml`, and the GitHub API reports no license | native extension | Avoid: unlicensed by default means all rights reserved |
| [`supermemo2`](https://pypi.org/project/supermemo2/) (PyPI, v3.0.1) | MIT | `attrs` | SM-2 |
| `ankitects/anki` | **AGPL-3.0-or-later** | — | Do not copy code from it |

### Is a dependency-free domain implementation realistic?

**SM-2: trivially yes.** The entire algorithm is ~15 lines, and SuperMemo's own reference implementation above is the spec. There is no reason to take a dependency.

**FSRS-6 scheduler: yes, realistically.** The scheduling math is the ~150 lines quoted in §1.2 — nine small pure functions over floats plus two derived constants. The maths uses only `math.exp` / `math.pow`, no arrays and no linear algebra. `fsrs/scheduler.py` is 858 lines total, but that includes docstrings, JSON serialization, parameter-bounds validation, fuzzing, and `reschedule_card`. The genuinely irreducible part is small.

The one real complexity is not the maths — it is `review_card`'s **learning/relearning step state machine** (~285 lines of `match card.state:` branching over `learning_steps`, `relearning_steps`, and the Again/Hard/Good/Easy cases). If the tutor schedules only in whole days and has no sub-day "learning steps" concept, this can be configured away with `learning_steps=()` (the code has an explicit `if len(self.learning_steps) == 0` branch straight to `State.Review`) — which cuts the port down to the pure DSR math and makes a pure-domain implementation genuinely small.

**FSRS optimizer: no.** `fsrs/optimizer.py` is 674 lines of PyTorch (BCELoss, Adam, cosine-annealing LR, backprop-through-time over review sequences). Nobody should reimplement that. Since §2 concludes we should ship with defaults anyway, this simply does not belong in the domain layer.

**MIT means either route is legally open.** The choice between "vendor `fsrs`" and "reimplement in domain" is architectural, not legal. Given the map's standing constraint that the domain layer be dependency-free and unit-testable without I/O mocks, and given that `py-fsrs`'s `review_card` reads `datetime.now()` by default and calls `random()` by default, **reimplementing is the better fit** — with `py-fsrs` retained as a **test oracle**: a dev-dependency used in tests to assert the domain implementation agrees with the reference on a table of cases. That gets correctness assurance without a runtime dependency.

---

## 4. Is SM-2 → FSRS migration cheap or a rewrite?

**Neither. It is cheap *if and only if* you keep an append-only review log.** The migration is a well-trodden path with first-class support in the FSRS codebase — `fsrs-rs/examples/migrate.rs` exists precisely for this and demonstrates **three** sanctioned paths:

1. **`migrate_with_full_history`** — replay every `(rating, delta_t)` through FSRS to compute the true current memory state. This is the good path, and it loses nothing. In Python this is a single call:

   ```python
   Scheduler.reschedule_card(card: Card, review_logs: list[ReviewLog]) -> Card
   ```

   which internally re-runs `review_card` over the sorted logs from a blank card. Its docstring: *"If the current card was previously scheduled with a different scheduler, you may want to reschedule/update it as if it had always been scheduled with this current scheduler."*

2. **`migrate_with_partial_history`** — seed from SM-2 values, then replay whatever history you have.

3. **`migrate_with_latest_state`** — no history at all; approximate memory state from the SM-2 numbers directly. FSRS ships a closed-form bridge for exactly this (`fsrs-rs/src/inference.rs`, comment: *"If a card has incomplete learning history, memory state can be approximated from current sm2 values"*):

   ```rust
   pub fn memory_state_from_sm2(&self, ease_factor: f32, interval: f32, sm2_retention: f32) -> Result<MemoryState> {
       let decay = -w[20];
       let factor = 0.9f32.powf(1.0 / decay) - 1.0;
       let stability = interval.max(S_MIN) * factor / (sm2_retention.powf(1.0 / decay) - 1.0);
       let difficulty = 11.0 - (ease_factor - 1.0)
           / (w[8].exp() * stability.powf(-w[9]) * ((1.0 - sm2_retention) * w[10]).exp_m1());
       ...
   }
   ```

   Note the shape: **stability is recoverable from `interval` almost exactly** (it is just an inverse of the forgetting curve at the assumed retention), while **difficulty is an inversion of the recall-stability formula from `ease_factor`** — a much lossier approximation, requiring you to *assume* the true retention SM-2 was achieving (`sm2_retention`, typically 0.9).

**So the cost profile is:**

| What you kept | Migration cost | Loss |
|---|---|---|
| Full `(concept, rating, reviewed_at)` review log | One batch job replaying logs | **None** — FSRS reconstructs exact memory state |
| Only current SM-2 fields | One closed-form formula per card | Difficulty is approximate; assumes a retention rate SM-2 never measured |
| Nothing (only `due_date`) | Reset all cards to new | Total history loss |

It is emphatically **not** a data-model rename: `ease_factor` and `stability` are not the same quantity in different units, `repetitions` has no FSRS counterpart, and `interval` becomes a derived output rather than stored state. The SQLite schema changes either way. Anki's manual also warns the switch is user-visible even when done correctly: "Reschedule cards on change … The default is not to reschedule cards: future reviews will use the new scheduling, but there will be no immediate change to your workload"; and it recommends backing up first. The FAQ notes the behavioural difference: "FSRS tends to give longer first intervals than SM-2, but for mature cards the opposite is true - FSRS is more conservative."

**The load-bearing conclusion for this project:** the migration risk is entirely controlled by **one schema decision made now** — whether `review_events(concept_id, rating, reviewed_at, duration_ms)` exists as an append-only table. That table is worth having regardless of the algorithm (it is the raw evidence for the map's still-open "knowledge-tracing model" question, and it is what any future optimizer consumes). With it, algorithm choice is reversible. Without it, it is not.

---

## Recommendation

**Implement FSRS-6 directly in the domain layer, using `DEFAULT_PARAMETERS`, with fuzzing off, and add an append-only `review_events` table in the same migration.**

Concretely:

- `SRSState(stability, difficulty, due, last_review, phase, step)` replaces `SRSMetadata(interval, repetitions, ease_factor, due_date)` in the PRD.
- `calculate_next_review(state: SRSState, rating: Rating, reviewed_at: datetime) -> SRSState` — a pure function; `reviewed_at` is a parameter, never a clock read, so tests need no I/O mocks.
- Keep the PRD's 1–4 rating scale — it is already FSRS's native scale, so nothing is invented.
- `parameters: tuple[float, ...]` and `desired_retention: float` are configuration on the engine, not per-card state. Ship the 21 published defaults.
- Configure `learning_steps=()` unless the tutor genuinely wants sub-day re-asks; that removes the bulk of the reference implementation's complexity.
- Add `py-fsrs` (MIT) as a **test-only** dependency and pin a differential test asserting the domain implementation matches `Scheduler(enable_fuzzing=False).review_card` across a table of `(state, rating, elapsed)` cases.
- Do **not** build parameter optimization now. Revisit only after the review log passes ~512–1000 events, and then as an offline CLI using the `fsrs[optimizer]` extra — never in the runtime path.

**Why not SM-2**, given it is simpler: SM-2's simplicity is real but its state is *not* meaningfully smaller (3 floats/ints vs 2 floats), its grade scale conflicts with the PRD's 1–4 buttons and would force an invented mapping, and it ignores elapsed time — which the tutor cannot, because a learner who returns after a three-week gap is exactly the case this system exists to handle. The reference SM-2 also has genuine spec ambiguities (§1.1) that every implementation resolves differently.

**The trade-off, stated plainly:**

FSRS costs roughly **10× the domain code** (~150 lines of interlocking exponential formulas with 21 magic constants, vs ~15 lines for SM-2), and those formulas are **empirical, not derivable** — a reviewer cannot check them by reasoning, only by differential-testing against the reference. That is a real hit to the "AI-navigable, readable domain layer" goal, and it is why the `py-fsrs` differential test is not optional but load-bearing.

What you buy for that: the algorithm that the benchmark shows is state-of-the-art among interpretable models, correct handling of late reviews, a native 1–4 scale, and a 21-float upgrade path (fit later, or not at all) that requires no schema change. And critically, the cost is **paid once and does not compound** — the FSRS math is a leaf function with no dependencies on the rest of the system.

The genuinely irreversible decision is not FSRS vs SM-2. It is the review log. Add it now.

---

## Sources

Primary, in order of authority for each claim:

- SuperMemo, [Algorithm SM-2](https://super-memory.com/english/ol/sm2.htm) — SM-2 formulas, 0–5 grade scale, EF floor of 1.3.
- SuperMemo, [SuperMemo 2 algorithm: source code](https://super-memory.com/english/ol/sm2source.htm) — the authoritative per-item record and `Repetition` procedure signature.
- `fsrs` v6.3.2 wheel from PyPI, source inspected: `fsrs/card.py`, `fsrs/scheduler.py`, `fsrs/rating.py`, `fsrs/state.py`, `fsrs/optimizer.py`, `fsrs/review_log.py`, `dist-info/licenses/LICENSE`, `dist-info/METADATA`.
- [open-spaced-repetition/py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) — MIT license.
- [open-spaced-repetition/fsrs-rs](https://github.com/open-spaced-repetition/fsrs-rs) — `src/inference.rs` (`memory_state_from_sm2`), `examples/migrate.rs` (three migration paths); BSD-3-Clause.
- [open-spaced-repetition/fsrs-rs-python](https://github.com/open-spaced-repetition/fsrs-rs-python) — no license declared (checked repo root, `Cargo.toml`, `pyproject.toml`, GitHub API).
- [open-spaced-repetition/srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark) README — benchmark methodology, dataset size, and the fitted-vs-default results table.
- [awesome-fsrs wiki, "The Algorithm"](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm) — FSRS-6 as current version, DSR variables, 21 parameters, 90% retention baseline.
- [fsrs4anki `docs/tutorial.md`](https://github.com/open-spaced-repetition/fsrs4anki/blob/main/docs/tutorial.md) — minimum-review history, "default parameters … better than SM-2", re-optimization cadence.
- [Anki manual, Deck Options](https://docs.ankiweb.net/deck-options.html) — "less than a few hundred" reviews, "Reschedule cards on change", "Ignore cards reviewed before", monthly optimization.
- [Anki FAQ, FSRS](https://faqs.ankiweb.net/frequently-asked-questions-about-fsrs.html) — no minimum reviews in 24.06.3+, FSRS vs SM-2 interval behaviour.
- [ankitects/anki `LICENSE`](https://github.com/ankitects/anki/blob/main/LICENSE) — AGPL-3.0-or-later.
- [`supermemo2` on PyPI](https://pypi.org/project/supermemo2/) — MIT, v3.0.1.
