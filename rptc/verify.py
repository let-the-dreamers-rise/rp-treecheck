"""Verify one rewards interval end to end.

  L1  tree: rebuild the Merkle root from the rewards file, check every proof, compare with the on-chain root
  L2  accounting: totals and per-network sums are consistent
  L3  RPL: recompute collateral and oDAO RPL for every node from EL state at targetElBlock
  L4  voter share: recompute each megapool node's voter share (RPIP-46)
  L5  smoothing pool: recompute node-operator ETH and SP voter share from the attestation scores
      in the performance file, and check each megapool validator's per-attestation score against
      its bond as the contracts record it
Usage: python -m rptc.verify <interval> <rewards.json> <performance.json> <el-cache.json> <bn-cache.json>
"""
import json, sys
from .filecheck import check_rewards_file
from .rpl import node_weight, ETH

STAKING = 2


def megapool_borrowed(n):
    mi = n.get("megapoolInfo")
    if not mi:
        return 0
    # Spec-gap note: the published trees count 28 ETH per staked, not-exited validator.
    return 28 * ETH * sum(1 for v in mi["validators"] if v["staked"] and not v["exited"])


def recompute_rpl(snap, bn, target_epoch):
    ratio, T, ts = int(snap["rplPrice"]), int(snap["intervalTime"]), int(snap["timestamp"])
    pend = int(snap["pendingRPL"])
    coll_total = pend * int(snap["perc"]["rocketClaimNode"]) // ETH
    odao_total = pend * int(snap["perc"]["rocketClaimTrustedNode"]) // ETH
    W = {}
    for a, n in snap["nodes"].items():
        b = sum(int(m["userDeposit"]) for m in n.get("minipools", {}).values()
                if m["status"] == STAKING and m["pubkey"] in bn and bn[m["pubkey"]]["exit_epoch"] > target_epoch)
        b += megapool_borrowed(n)
        w = node_weight(b, int(n["staked"]), ratio) or 0
        age = ts - int(n["regTime"])
        if age < T:
            w = w * age // T
        if w:
            W[a.lower()] = w
    tw = sum(W.values())
    coll = {a: coll_total * w // tw for a, w in W.items()}
    part = {m.lower(): min(T, ts - int(j)) for m, j in snap["odao"].items()}
    tp = sum(part.values())
    odao = {m: odao_total * p // tp for m, p in part.items()}
    return coll, odao, tw


def vote_eligible(snap):
    ratio = int(snap["rplPrice"])
    VE = {}
    for a, n in snap["nodes"].items():
        mi = n.get("megapoolInfo")
        if not mi or not any(v["staked"] and not v["exited"] for v in mi["validators"]):
            continue
        cap = int(n["megapoolBonded"]) * 15 // 10 * ETH // ratio  # 1.5 x RPL value of bonded ETH
        ve = min(cap, int(n["megapoolStaked"]))
        if ve:
            VE[a.lower()] = ve
    return VE


def cmp(name, mine, pub):
    keys = set(mine) | set(pub)
    bad = [k for k in keys if mine.get(k, 0) != pub.get(k, 0)]
    return (name, not bad, f"{len(keys) - len(bad)}/{len(keys)} exact" + (f"; e.g. {bad[:3]}" if bad else ""))


def verify(rf, pf, snap, bn, onchain_root=None):
    out = check_rewards_file(rf)
    if onchain_root:
        out.append(("root equals on-chain rewards.merkle.root", onchain_root.lower() == rf["merkleRoot"].lower(), onchain_root))
    nr = {a.lower(): v for a, v in rf["nodeRewards"].items()}
    te = rf["consensusEndBlock"] // 32
    coll, odao, tw = recompute_rpl(snap, bn, te)
    out.append(("L3 totalNodeWeight", tw == int(rf["totalRewards"]["totalNodeWeight"]), f"{tw}"))
    out.append(cmp("L3 collateral RPL per node", coll, {a: int(v["collateralRpl"]) for a, v in nr.items() if int(v["collateralRpl"])}))
    out.append(cmp("L3 oDAO RPL per node", {k: v for k, v in odao.items() if v}, {a: int(v["oracleDaoRpl"]) for a, v in nr.items() if int(v["oracleDaoRpl"])}))
    t = rf["totalRewards"]
    if rf["rulesetVersion"] >= 11:
        VE = vote_eligible(snap)
        pool = int(snap["pendingVoterShare"]) + int(t.get("smoothingPoolVoterShareEth", 0))
        tot = sum(VE.values())
        vs = {a: pool * v // tot for a, v in VE.items()} if tot else {}
        out.append(cmp("L4 voter share per node", {k: v for k, v in vs.items() if v}, {a: int(v["voterShareEth"]) for a, v in nr.items() if int(v.get("voterShareEth", 0))}))
    out += check_sp(rf, pf, snap)
    return out


def check_sp(rf, pf, snap):
    out = []
    t = rf["totalRewards"]
    SP = int(t["totalSmoothingPoolEth"])
    mps = pf.get("minipoolPerformance", {})
    mvs = {m: p["validatorPerformance"] for m, p in pf.get("megapoolPerformance", {}).items() if "validatorPerformance" in p}
    allv = list(mps.values()) + [x for p in mvs.values() for x in p.values()]
    A = sum(v["successfulAttestations"] for v in allv)
    S = sum(int(v["attestationScore"]) for v in allv)
    if not A:
        return out
    tno = SP * S // (A * ETH)
    earned_ok = all(tno * int(v["attestationScore"]) // S == int(v["ethEarned"]) for v in allv)
    out.append(("L5 per-validator SP ETH from scores", earned_ok, f"{len(allv)} validators"))
    out.append(("L5 NO SP ETH total", sum(tno * int(v["attestationScore"]) // S for v in allv) == int(t["nodeOperatorSmoothingPoolEth"]), ""))
    if mvs:
        byaddr = {n["megapool"].lower(): n for n in snap["nodes"].values() if n.get("megapoolInfo")}
        f_no, f_v = 5 * ETH // 100, 9 * ETH // 100  # TODO read time-weighted split from RocketNetworkRevenues
        wrong = []
        for m, vals in mvs.items():
            mi = byaddr[m.lower()]["megapoolInfo"]
            funded = sum(1 for v in mi["validators"] if not v["exited"] and not v["dissolved"] and not v["inQueue"])
            b = int(mi["nodeBond"]) // funded if funded else 0
            want = (ETH * b + 32 * ETH * f_no - f_no * b) // (32 * ETH)
            for x in vals.values():
                if x["successfulAttestations"] and int(x["attestationScore"]) != x["successfulAttestations"] * want:
                    wrong.append(m)
                    break
        out.append(("L5 megapool score uses each staking validator's own bond", not wrong,
                    f"{len(mvs) - len(wrong)}/{len(mvs)} megapools ok" + (f"; {len(wrong)} scored with nodeBond/activeValidatorCount (queued validators counted)" if wrong else "")))
    return out


if __name__ == "__main__":
    n, rfp, pfp, elp, bnp = sys.argv[1:6]
    root = sys.argv[6] if len(sys.argv) > 6 else None
    res = verify(json.load(open(rfp)), json.load(open(pfp)), json.load(open(elp)), json.load(open(bnp)), root)
    for name, ok, detail in res:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
