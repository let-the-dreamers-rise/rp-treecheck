# rp-treecheck

An independent check of Rocket Pool's per-interval rewards trees, written from the specs (the v10 rewards spec, the Merkle tree spec, RPIP-43 and RPIP-46), not from treegen's code.

For a published interval it:

1. rebuilds the Merkle root from the rewards file, checks every proof, and compares the root with the one stored on-chain
2. checks the file's accounting (totals, per-network sums)
3. recomputes collateral RPL and oDAO RPL for every node from execution-layer state at `targetElBlock`
4. recomputes megapool voter share for every node (RPIP-46)
5. recomputes smoothing-pool ETH from the attestation scores, and checks each megapool score against the validator's real bond

Results and open issues: [FINDINGS.md](FINDINGS.md).

```
pip install -r requirements.txt
python -m rptc.run 54            # one interval (about 10 min; uses public archive RPC + beacon API)
python -m pytest -q              # mutation tests on real trees
```

The endpoints default to public ones. Set `RPTC_RPC` (archive EL) and `RPTC_BEACON` to use your own.

CI runs daily and verifies the latest interval as soon as its root is on-chain.

MIT licensed.
