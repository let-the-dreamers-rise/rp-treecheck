# rp-treecheck findings (mainnet, rulesets v10–v11)

Method: every amount below was recomputed from public data only (the published rewards and
performance files, EL state at each interval's `targetElBlock` read through an archive RPC,
and validator epochs from the beacon head state), following the v10 rewards spec (RPIP-62 asset),
the Merkle tree spec (RPIP-53 asset), RPIP-43 and RPIP-46. treegen's Go code was **not** used to
write the checker. It was read only after a mismatch, to find the root cause.

## What reproduces exactly (interval 54)

| Check | Result |
|---|---|
| Merkle root rebuilt from the rewards file, equal to `rewards.merkle.root` stored on-chain | exact |
| All 1,373 published Merkle proofs | 1,373 / 1,373 verify |
| `totalNodeWeight` | exact to the wei |
| Collateral RPL per node | 1,278 / 1,278 exact |
| oDAO RPL per node | 10 / 10 exact |
| Megapool voter share per node (RPIP-46) | 89 / 89 exact |
| Smoothing-pool ETH per validator, given the attestation scores | 8,966 / 8,966 exact |

The tree checks (L1 and L2) also pass for intervals 44–49. For 50–54, the only failure is F3.

## F1. Megapool smoothing-pool commission is computed with the wrong bond when a megapool has queued validators

**Where:** `treeGeneratorImpl_v11`, megapool attestation score. The bond per validator comes from
`GetMegapoolBondNormalized()`, which is `nodeBond / ActiveValidatorCount`.

**The problem:** in `RocketMegapoolDelegate`:
- `nodeBond` grows only when the deposit pool assigns funds (`assignFunds`: `nodeBond += assignedNodeBond`).
- The bond of a validator still in the queue sits in `nodeQueuedBond`.
- `getActiveValidatorCount()` is `numValidators - numInactiveValidators`, which **includes queued validators**.

So a megapool with 2 staking validators (4 ETH bond each) and 12 queued validators gets
8 ETH / 14 = 0.571 ETH as its "bond", not 4 ETH. Every attestation from its 2 running validators
is then scored as if almost all of their capital were borrowed:
- The operator's per-attestation score falls from 0.16875 to 0.0670.
- The voter-share score rises.

**Impact (interval 54):**
- 36 of the 97 megapools in the smoothing pool were scored with a bond below their real one.
- 31 node operators were underpaid, by 0.0308 ETH in total.
- The largest single shortfall was 0.0073 ETH. That node had 41 staking and 113 queued validators, and was scored with a 1.065 ETH bond instead of 4 ETH.
- The money went to the SP voter share and to rETH instead.

The dollar amounts are small today because the queue is short and megapool SP income is small.
The error grows with queue length.

Per interval: 50 → 26 nodes, 0.0189 ETH; 52 → 31 nodes, 0.0254 ETH; 54 → 31 nodes, 0.0308 ETH (51 and 53 pending). The published scores are reproduced exactly with `nodeBond / getActiveValidatorCount()`, which confirms the mechanism.

This is outside Rocket Pool's Immunefi scope, which covers smart contracts only, so it can be reported publicly.

**Spec basis:**
- RPIP-46: "each node operator receives this percentage of the commission from the borrowed ETH on validators they run".
- The v10 spec's score formula uses the bond of the validator that performed the duty.
- The contracts' own capital ratio (`_calculateAndSaveCapitalRatio`) uses `nodeBond` against `userCapital`, both assigned values. So treegen also disagrees with the contracts.

**Suggested fix:** divide `nodeBond` by the number of validators that have been assigned funds and have not exited or been dissolved. Equivalently, exclude `inQueue` validators from the denominator.

## F2. Ruleset v11 has no written specification

- The newest written rewards spec is v10 (RPIP-62 asset, 2024).
- Mainnet has used v11 since interval 46. The v11 rules exist only in `generator-impl-v11.go`.
- v2–v10 each had a forum spec thread and an RPIP asset. v11 has neither.

Rules I had to reverse-engineer from published trees (each is now a test in rp-treecheck):
1. **Leaf format** (tree version 1): `address ++ network ++ totalRPL ++ smoothingPoolETH ++ voterShareETH`, 148 bytes. It is confirmed by `RocketMerkleDistributorMainnet._verifyProof`. The Merkle tree spec still documents the 116-byte leaf.
2. **Borrowed ETH for RPL weight:** megapools count **28 ETH per staked, not-exited validator**. The contract getter `getNodeMegapoolETHBorrowed` is not used, because it includes queued validators. Using the getter changes 43 nodes and inflates total weight by 11%.
3. **Vote-eligible RPL (RPIP-46)** uses `getNodeMegapoolETHBonded`, which includes queued bonds, but only for nodes with at least one staked validator. This is inconsistent with rule 2: queued validators count toward the voter-share cap but not toward RPL weight.
4. **Voter share pool** = `getPendingVoterShare()` + SP voter share, split pro rata by vote-eligible RPL with one floor division per node. The rounding dust (41 wei in interval 54) is left undistributed.
5. Nodes with staked RPL but no eligible borrowed ETH get zero weight. The v10 formula divides by `eligibleBorrowedEth`, so this case is undefined in the written spec.

## F3. Rewards-file totals do not add up since interval 50 (cosmetic)

`poolStakerSmoothingPoolEth + nodeOperatorSmoothingPoolEth + smoothingPoolVoterShareEth` exceeds
`totalSmoothingPoolEth` by 41–45 wei in every interval from 50 to 54. Interval 50 is the first one with
SP voter share.

`smoothingPoolVoterShareEth` is the pre-rounding figure. The amounts actually allocated (leaves, and
`userETH`/`nodeETH` in the on-chain `RewardSnapshot`) balance exactly. No funds are affected. The
metadata just should not claim more than the pool held.

## F4. Interval 22 (history, already public)

In interval 22, the two treegen code paths disagreed about late attestations, and the tree that was
finalised followed the written spec but not the beacon spec (topic 2974). This was the last time an
independent implementation (rockettree) was used to cross-check a tree. That implementation stopped at v10.
