"""Layer 1 + 2: rebuild the Merkle tree from a published rewards file and check its accounting.

Needs only the published files. Each check returns (name, ok, detail).
"""
import json
from .merkle import leaf, leaf_v1, build, verify, NULL

def _i(x):
    return int(x)


def leaf_for(rf, addr, v):
    rpl = _i(v["collateralRpl"]) + _i(v["oracleDaoRpl"])
    if rf.get("rulesetVersion", 0) >= 11:
        # tree version 1 (Saturn 1): RocketMerkleDistributorMainnet._verifyProof
        return leaf_v1(addr, v["rewardNetwork"], rpl, _i(v["smoothingPoolEth"]), _i(v.get("voterShareEth", 0)))
    return leaf(addr, v["rewardNetwork"], rpl, _i(v["smoothingPoolEth"]))


def check_rewards_file(rf):
    out = []
    nr = rf["nodeRewards"]
    leaves = {a: leaf_for(rf, a, v) for a, v in nr.items()}
    levels = build(list(leaves.values()))
    root = levels[-1][0]
    out.append(("merkle root reproduces", root.hex() == rf["merkleRoot"][2:].lower(), "0x" + root.hex()))
    bad = [a for a, v in nr.items() if not verify(leaves[a], [bytes.fromhex(p[2:]) for p in v["merkleProof"]], root)]
    out.append(("every published proof verifies", not bad, f"{len(nr) - len(bad)}/{len(nr)} ok" + (f"; bad: {bad[:5]}" if bad else "")))
    lower = [a for a in nr if a != a.lower()]
    out.append(("claimer addresses unique", len({a.lower() for a in nr}) == len(nr), f"{len(nr)} claimers"))
    zero = [a for a, v in nr.items() if all(_i(v.get(k, 0)) == 0 for k in ("collateralRpl", "oracleDaoRpl", "smoothingPoolEth", "voterShareEth"))]
    out.append(("no all-zero claimers", not zero, f"{len(zero)} zero leaves" + (f": {zero[:3]}" if zero else "")))
    t = rf["totalRewards"]
    s = lambda k: sum(_i(v.get(k, 0)) for v in nr.values())
    out.append(("sum collateralRpl == totalCollateralRpl", s("collateralRpl") == _i(t["totalCollateralRpl"]), f"{s('collateralRpl')} vs {t['totalCollateralRpl']}"))
    out.append(("sum oracleDaoRpl == totalOracleDaoRpl", s("oracleDaoRpl") == _i(t["totalOracleDaoRpl"]), f"{s('oracleDaoRpl')} vs {t['totalOracleDaoRpl']}"))
    if "nodeOperatorSmoothingPoolEth" in t:
        spv = _i(t.get("smoothingPoolVoterShareEth", 0))
        pd = _i(t.get("totalPdaoShareEth", 0))
        tot = _i(t["poolStakerSmoothingPoolEth"]) + _i(t["nodeOperatorSmoothingPoolEth"]) + spv + pd
        out.append(("SP split conserves ETH (staker + NO + voter + pDAO == total)", tot == _i(t["totalSmoothingPoolEth"]), f"{tot} vs {t['totalSmoothingPoolEth']}"))
    if "totalVoterShareEth" in t:
        net_sp = sum(_i(n["smoothingPoolEth"]) for n in rf["networkRewards"].values())
        exp = _i(t["nodeOperatorSmoothingPoolEth"]) + _i(t["totalVoterShareEth"])
        out.append(("network smoothingPoolEth == NO SP ETH + total voter share", net_sp == exp, f"{net_sp} vs {exp}"))
        out.append(("sum leaf ETH == network smoothingPoolEth", s("smoothingPoolEth") + s("voterShareEth") == net_sp, f"{s('smoothingPoolEth') + s('voterShareEth')} vs {net_sp}"))
        out.append(("sum voterShareEth == totalVoterShareEth", s("voterShareEth") == _i(t["totalVoterShareEth"]), f"{s('voterShareEth')} vs {t['totalVoterShareEth']}"))
        out.append(("sum node smoothingPoolEth == nodeOperatorSmoothingPoolEth", s("smoothingPoolEth") == _i(t["nodeOperatorSmoothingPoolEth"]), f"{s('smoothingPoolEth')} vs {t['nodeOperatorSmoothingPoolEth']}"))
    for netid, n in rf["networkRewards"].items():
        out.append((f"network {netid} collateralRpl matches total", _i(n["collateralRpl"]) == _i(t["totalCollateralRpl"]), ""))
    return out


def check_performance(rf, pf):
    """Cross-checks between the rewards file and the performance file."""
    out = []
    t = rf["totalRewards"]
    vs = sum(_i(v["voterShare"]) for v in pf.get("megapoolPerformance", {}).values() if "voterShare" in v)
    if "megapoolPerformance" in pf:
        out.append(("perf: sum megapool voterShare (non-SP) present", True, str(vs)))
    return out
