# Capture source credibility signals; never store a credibility score

`WIKI_SPEC.md` §5.1 defines objective per-source signals — `author`,
`usage_count`, `last_modified`, `usage_window` — and explicitly refuses to
store a credibility *score*, because "a score is subjective, unportable
across consumers, and goes stale." Credibility is inferred by the consumer,
the way trust tiers are. Nothing in the pipeline populated those signals:
`IngestRawMaterial` wrote `Source(resource=…)` and dropped everything else,
so every credibility field in the vault was empty. We now populate the
signals at parse time and let `RelevanceCurator` — a consumer — infer from
them, rather than persisting any score it computes.

## Consequences

- **The signals must be captured at parse time or not at all.** A source
  document's author and modification date are cheaply available while it is
  being parsed and expensive to reconstruct afterwards. This is the reason
  the decision is hard to reverse: concepts ingested before the change carry
  no signals, and no later pass can recover them.
- **Unknown credibility must never be penalised.** Most existing concepts,
  and every note dropped into the inbox by hand, will have no signals at all.
  A curator that treats absent signals as low credibility would reject the
  vault's entire existing corpus and most future human input. Absent means
  *unknown*, and unknown must be neutral.
- **`usage_count` stays empty for now.** It measures how often a *source* was
  exercised. Concept usage by the learner is episodic and lives in `tutor`
  (see `CONTEXT.md`), so it is not written here — that would be the first
  exception to the semantic/episodic boundary, and it was declined.
- **A score computed by the curator is not persisted.** It informs an
  accept/reject decision at ingest and is then discarded, keeping the vault
  free of a number that would immediately begin going stale.
