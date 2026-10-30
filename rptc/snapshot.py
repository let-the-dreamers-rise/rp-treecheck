"""Fetch the execution-layer state a rewards interval depends on, at targetElBlock.

Only public contract getters are used (named in the rewards spec, RPIP-43 and RPIP-46).
The result is cached as JSON so the calculation itself is offline and reproducible.
"""
import json, os, sys
from .chain import contract, call, multicall, rpc

U = ["uint256"]
A = ["address"]


def fetch(block):
    c = {n: contract(n, block) for n in [
        "rocketNodeManager", "rocketNodeStaking", "rocketRewardsPool", "rocketNetworkPrices",
        "rocketDAONodeTrusted", "rocketSmoothingPool", "rocketMinipoolManager"]}
    nm, ns, mm = c["rocketNodeManager"], c["rocketNodeStaking"], c["rocketMinipoolManager"]
    hdr = rpc("eth_getBlockByNumber", [hex(block), False])
    s = {"block": block, "timestamp": int(hdr["timestamp"], 16), "contracts": c}
    rp = c["rocketRewardsPool"]
    s["rplPrice"] = call(c["rocketNetworkPrices"], "getRPLPrice()", [], U, block)[0]
    s["intervalTime"] = call(rp, "getClaimIntervalTime()", [], U, block)[0]
    s["intervalStart"] = call(rp, "getClaimIntervalTimeStart()", [], U, block)[0]
    s["pendingRPL"] = call(rp, "getPendingRPLRewards()", [], U, block)[0]
    s["pendingVoterShare"] = call(rp, "getPendingVoterShare()", [], U, block)[0]
    s["perc"] = {n: call(rp, "getClaimingContractPerc(string)", [n], U, block)[0]
                 for n in ["rocketClaimNode", "rocketClaimTrustedNode", "rocketClaimDAO"]}
    n = call(nm, "getNodeCount()", [], U, block)[0]
    nodes = [r[0] for r in multicall([(nm, "getNodeAt(uint256)", [i], A) for i in range(n)], block)]
    per = {}
    for name, to, sig, out in [
        ("staked", ns, "getNodeStakedRPL(address)", U),
        ("legacyStaked", ns, "getNodeLegacyStakedRPL(address)", U),
        ("megapoolStaked", ns, "getNodeMegapoolStakedRPL(address)", U),
        ("unstaking", ns, "getNodeUnstakingRPL(address)", U),
        ("minipoolBorrowed", ns, "getNodeMinipoolETHBorrowed(address)", U),
        ("megapoolBorrowed", ns, "getNodeMegapoolETHBorrowed(address)", U),
        ("megapoolBonded", ns, "getNodeMegapoolETHBonded(address)", U),
        ("regTime", nm, "getNodeRegistrationTime(address)", U),
        ("spState", nm, "getSmoothingPoolRegistrationState(address)", ["bool"]),
        ("spChanged", nm, "getSmoothingPoolRegistrationChanged(address)", U),
        ("megapool", nm, "getMegapoolAddress(address)", A),
        ("rplWithdrawal", nm, "getNodeRPLWithdrawalAddress(address)", A),
        ("minipoolCount", mm, "getNodeMinipoolCount(address)", U),
    ]:
        r = multicall([(to, sig, [a], out) for a in nodes], block)
        per[name] = [x[0] if x else None for x in r]
    s["nodes"] = {}
    for i, a in enumerate(nodes):
        s["nodes"][a] = {k: (str(v[i]) if isinstance(v[i], int) and not isinstance(v[i], bool) else v[i]) for k, v in per.items()}
    # minipools
    idx = [(a, j) for a in nodes for j in range(int(s["nodes"][a]["minipoolCount"]))]
    mps = multicall([(mm, "getNodeMinipoolAt(address,uint256)", [a, j], A) for a, j in idx], block)
    mps = [m[0] for m in mps]
    st = multicall([(m, "getStatus()", [], ["uint8"]) for m in mps], block)
    ud = multicall([(m, "getUserDepositBalance()", [], U) for m in mps], block)
    nd = multicall([(m, "getNodeDepositBalance()", [], U) for m in mps], block)
    fee = multicall([(m, "getNodeFee()", [], U) for m in mps], block)
    pk = multicall([(mm, "getMinipoolPubkey(address)", [m], ["bytes"]) for m in mps], block)
    for (a, _), m, x1, x2, x3, x4, x5 in zip(idx, mps, st, ud, nd, fee, pk):
        s["nodes"][a].setdefault("minipools", {})[m] = {
            "status": x1[0] if x1 else None, "userDeposit": str(x2[0]) if x2 else None,
            "nodeDeposit": str(x3[0]) if x3 else None, "fee": str(x4[0]) if x4 else None,
            "pubkey": x5[0].hex() if x5 else None}
    # oDAO
    od = c["rocketDAONodeTrusted"]
    k = call(od, "getMemberCount()", [], U, block)[0]
    mem = [r[0] for r in multicall([(od, "getMemberAt(uint256)", [i], A) for i in range(k)], block)]
    jt = multicall([(od, "getMemberJoinedTime(address)", [m], U) for m in mem], block)
    s["odao"] = {m: str(j[0]) for m, j in zip(mem, jt)}
    return s


if __name__ == "__main__":
    block, out = int(sys.argv[1]), sys.argv[2]
    s = fetch(block)
    json.dump(s, open(out, "w"))
    print(out, len(s["nodes"]), "nodes", sum(len(n.get("minipools", {})) for n in s["nodes"].values()), "minipools")


VINFO = "(uint32,uint32,uint32,uint32,bool,bool,bool,bool,bool,bool,bool,bool,uint64,uint64)"
VKEYS = ["lastAssignmentTime", "lastRequestedValue", "lastRequestedBond", "depositValue", "staked", "exited",
         "inQueue", "inPrestake", "expressUsed", "dissolved", "exiting", "locked", "exitBalance", "lockedTime"]


def fetch_megapools(snap):
    """Per-validator megapool state (RPIP-43), added to an existing snapshot."""
    block = snap["block"]
    mps = [(a, n["megapool"]) for a, n in snap["nodes"].items() if n["megapool"] and int(n["megapool"], 16)]
    cnt = multicall([(m, "getValidatorCount()", [], ["uint32"]) for _, m in mps], block)
    idx = [(a, m, i) for (a, m), c in zip(mps, cnt) if c for i in range(c[0])]
    info = multicall([(m, "getValidatorInfoAndPubkey(uint32)", [i], [VINFO, "bytes"]) for _, m, i in idx], block)
    extra = {}
    for name, sig, t in [("nodeBond", "getNodeBond()", "uint256"), ("userCapital", "getUserCapital()", "uint256"),
                         ("debt", "getDebt()", "uint256"), ("activeValidatorCount", "getActiveValidatorCount()", "uint32")]:
        r = multicall([(m, sig, [], [t]) for _, m in mps], block)
        for (a, m), x in zip(mps, r):
            extra.setdefault(a, {})[name] = (x[0] if t == "uint32" else str(x[0])) if x else None
    for a, m in mps:
        snap["nodes"][a]["megapoolInfo"] = dict(extra.get(a, {}), validators=[])
    for (a, m, i), r in zip(idx, info):
        if r is None:
            continue
        v = dict(zip(VKEYS, r[0]))
        v["pubkey"] = r[1].hex()
        v["id"] = i
        snap["nodes"][a]["megapoolInfo"]["validators"].append(v)
    return snap
