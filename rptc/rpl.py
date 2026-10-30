"""RPL issuance rewards (collateral + oDAO + pDAO), written from the v10 rewards spec
(RPIP-62 asset) as amended for Saturn 1 by RPIP-46 ("All staked RPL SHALL be counted ...
both legacy staked RPL and megapool staked RPL").

Inputs: an EL snapshot (snapshot.py) and the set of eligible minipools (exit_epoch > target epoch).
Every interpretation choice that the written spec does not settle is a named option, so the
same code can test competing readings against the published tree.
"""
ETH = 10 ** 18
STAKING = 2  # MinipoolStatus.Staking


def log2(x):
    # spec: iterative approximation, 60 inner loops, fixed point 1e18
    result = 0
    exponent = 0
    while (x >> (exponent + 1)) >= ETH:
        exponent += 1
    result += exponent * ETH
    y = x >> exponent
    if y == ETH:
        return result
    delta = ETH
    for _ in range(60):
        delta //= 2
        y = y * y // ETH
        if y >= 2 * ETH:
            result += delta
            y //= 2
    return result


def ln(x):
    return log2(x) * ETH // 1442695040888963407


def node_weight(eligible_borrowed, stake, ratio):
    staked_value = stake * ratio // ETH
    if eligible_borrowed == 0:
        return None  # spec divides by eligibleBorrowedEth; undefined (see SPEC-GAPS)
    pct = staked_value * 100 * ETH // eligible_borrowed
    if pct <= 15 * ETH:
        return 100 * staked_value
    return (13613700000000000000 + 2 * ln(pct - 13 * ETH)) * eligible_borrowed // ETH


def compute(snap, eligible_pubkeys, opts=None):
    o = {"stake": "staked", "megapool_borrowed": "contract", "zero_borrowed": "skip"}
    o.update(opts or {})
    ratio = int(snap["rplPrice"])
    T = int(snap["intervalTime"])
    ts = int(snap["timestamp"])
    pending = int(snap["pendingRPL"])
    perc = {k: int(v) for k, v in snap["perc"].items()}
    collateral = pending * perc["rocketClaimNode"] // ETH
    odao_total = pending * perc["rocketClaimTrustedNode"] // ETH
    weights = {}
    for addr, n in snap["nodes"].items():
        b = 0
        for m, mp in n.get("minipools", {}).items():
            if mp["status"] == STAKING and mp["pubkey"] and mp["pubkey"] in eligible_pubkeys:
                b += int(mp["userDeposit"])
        if o["megapool_borrowed"] == "contract":
            b += int(n["megapoolBorrowed"] or 0)
        if o["stake"] == "staked":
            stake = int(n["staked"])
        elif o["stake"] == "legacy+megapool":
            stake = int(n["legacyStaked"]) + int(n["megapoolStaked"])
        elif o["stake"] == "staked+unstaking":
            stake = int(n["staked"]) + int(n["unstaking"] or 0)
        w = node_weight(b, stake, ratio)
        if w is None:
            w = 0
        age = ts - int(n["regTime"])
        if age < T:
            w = w * age // T
        if w:
            weights[addr] = w
    total_w = sum(weights.values())
    coll = {a: collateral * w // total_w for a, w in weights.items()}
    part = {m: min(T, ts - int(j)) for m, j in snap["odao"].items()}
    tp = sum(part.values())
    odao = {m: odao_total * p // tp for m, p in part.items()}
    return {"collateral": coll, "odao": odao, "totalNodeWeight": total_w,
            "pdao": pending - sum(coll.values()) - sum(odao.values())}
