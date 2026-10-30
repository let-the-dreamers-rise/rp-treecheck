**Title:** v11 treegen: megapool SP score divides nodeBond by a validator count that includes queued validators

**Body:**

I've been building an independent implementation of the v11 rewards tree, written from the v10 spec plus RPIP-43 and RPIP-46, and checking it against published mainnet trees. Interval 54 reproduces to the wei for RPL, oDAO and voter share. One thing does not, and I think it is a treegen bug.

**What happens**

`treeGeneratorImpl_v11` scores each megapool attestation with `bond := details.GetMegapoolBondNormalized()`, which is `NodeBond / ActiveValidatorCount` (`bindings/utils/state/megapool.go`).

In `RocketMegapoolDelegate`:
- `nodeBond` only increases in `assignFunds()`. A queued validator's bond is in `nodeQueuedBond`.
- `getActiveValidatorCount()` is `numValidators - numInactiveValidators`, so it counts validators that are still `inQueue`.

So a megapool with queued validators gets a per-validator bond that is too low. Its running validators are then scored as if more of their capital were borrowed. The operator gets less of the smoothing pool, and the SP voter share and rETH get more.

**Example: interval 54, node 0x9c1609ff0e0c0ad2c3d27e4f5aeef85e57517064**
- At `executionEndBlock` 26246103, the megapool has `nodeBond` = 8 ETH, 2 staked validators and 12 in queue, and `getActiveValidatorCount()` returns 14.
- Bond used: 8 / 14 = 0.571 ETH. The real bond is 4 ETH.
- Per-attestation score in `rp-performance-mainnet-54.json`: 0.06701 (with 4 ETH it would be 0.16875).

**Scale in interval 54**
- 36 of 97 SP megapools were affected.
- 31 operators were underpaid by 0.0308 ETH in total. The largest shortfall was 0.0073 ETH, for node 0xc0e7…11ac: 41 staked and 113 queued validators, scored with a 1.065 ETH bond.

Small today, but it grows with the queue. It also happened in intervals 50 (26 operators, 0.019 ETH) and 52 (31 operators, 0.025 ETH). Per-interval reports: https://github.com/let-the-dreamers-rise/rp-treecheck/tree/main/reports

**Suggested fix**
Normalise by the validators that have been assigned funds and have not exited or been dissolved. Equivalently, exclude `inQueue` from the count. That matches how the contract computes its own capital ratio (`nodeBond` vs `userCapital`).

**Reproduce**
[rp-treecheck](https://github.com/let-the-dreamers-rise/rp-treecheck) recomputes this from public data. `python -m rptc.verify 54 …` prints the affected megapools.

Happy to help test a fix against the next tree.

