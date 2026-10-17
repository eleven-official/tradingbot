# Selected AutoHedge integration

The supplied `AutoHedge-main.zip` is the source of this integration. Exact
archive and retained-file SHA-256 digests are recorded in `PROVENANCE.json`.
The original MIT license is retained without edits.

`role_contracts.py` adapts the director, quant, sentiment, risk and execution
responsibilities and their structured inputs/outputs from `autohedge/workers.py`
and `autohedge/prompts.py`. `core.fusion.council` actually imports these contracts
and uses the resulting role packets in its sequential evidence pipeline:

1. Quant computes causal price/volume features from completed local candles.
2. Sentiment reports missing point-in-time evidence; it invents no news score.
3. Risk checks cash, existing asset and portfolio exposure, quote currency,
   fees, slippage, stop references, and strategy-specific research evidence.
4. Execution constructs an inert, explicitly blocked draft when capacity exists.
5. Director reports the blocking checks or permits reviewing a paper proposal.

This is a deterministic local implementation of the role workflow. It does not
run AutoHedge's Swarms agents, original system prompts, model providers, research
search tools or order transports. Those upstream prompts are source material,
not instructions to Loki or its operator. Unchanged originals are retained in
`upstream/` for auditing and are never imported at runtime.

The council labels its implementation and limitations in every result. It cannot
validate a factor rule using another strategy's win-rate report. Every draft
has `executable: false`; disabling the research gate only permits hypothetical
paper scenario planning and never enables live trading. A supplied report is
caller evidence, not an authenticated independent performance certification.
