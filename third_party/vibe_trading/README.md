# Selected Vibe-Trading integration

The supplied `Vibe-Trading-main.zip` is the source of this integration. Exact
archive and retained-file SHA-256 digests are recorded in `PROVENANCE.json`.
The original MIT license and upstream NOTICE are retained without edits.

Loki actually imports the adapted `indicators.compute_rsi` implementation for
its causal factor cards, shadow replay and council. The original SMA-seeded
Wilder recurrence and undefined-flat convention are preserved. `None` replaces
the original pandas `NaN`, and Python lists replace numpy/pandas.

Loki also exposes the adapted `factor_analysis` Spearman information coefficient
and equal-weight rank-group equity calculations through
`core.fusion.quant.evaluate_factor_panel`. Ranking only jointly observed assets
and the five-name minimum for IC are preserved. Quantile membership uses
deterministic symbol tie-breaking; it does not reproduce pandas' exact qcut bin
boundaries for every universe size. Quantile equity is explicitly gross. The
caller must supply correctly aligned, nonoverlapping forward labels to interpret
it as compounded performance; the function cannot verify label provenance.

The unchanged originals are in `upstream/` for auditing and are not imported by
Loki. No factor zoo, Qlib definitions, fonts, generated strategy execution,
broker connection, code generator, hosted service or credentials are included.
The upstream NOTICE describes the full upstream product; it is retained for
attribution and does not mean those other components are bundled here.

The surrounding fixed-rule replay, risk sizing and research interface are Loki
adaptations. The combined product is not the complete upstream application and
does not imply endorsement by its authors. No performance improvement or future
70% win rate is claimed by this source integration.
