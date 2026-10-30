"""Fetch everything for one interval and verify it: python -m rptc.run [interval]"""
import json, os, sys, urllib.request
from . import snapshot, beacon
from .chain import call, ROCKET_STORAGE, rpc
from .merkle import keccak256
from .verify import verify

RAW = "https://raw.githubusercontent.com/rocket-pool/rewards-trees/main/mainnet/"
CACHE = "cache"


def get(name):
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        urllib.request.urlretrieve(RAW + name, path)
    return json.load(open(path))


def latest():
    head = int(rpc("eth_blockNumber", []), 16)
    n = 0
    while True:  # first index whose root is not set yet
        k = keccak256(b"rewards.merkle.root" + (n + 1).to_bytes(32, "big"))
        if call(ROCKET_STORAGE, "getBytes32(bytes32)", [k], ["bytes32"], head)[0] == b"\0" * 32:
            return n
        n += 1


def main(n):
    rf = get(f"rp-rewards-mainnet-{n}.json")
    pf = get(f"rp-performance-mainnet-{n}.json")
    el = os.path.join(CACHE, f"el-{n}.json")
    if not os.path.exists(el):
        s = snapshot.fetch_megapools(snapshot.fetch(rf["executionEndBlock"]))
        json.dump(s, open(el, "w"))
    snap = json.load(open(el))
    bnp = os.path.join(CACHE, f"bn-{n}.json")
    if not os.path.exists(bnp):
        pks = [m["pubkey"] for x in snap["nodes"].values() for m in x.get("minipools", {}).values() if m["status"] == 2 and m["pubkey"]]
        json.dump(beacon.validators(pks), open(bnp, "w"))
    bn = json.load(open(bnp))
    head = int(rpc("eth_blockNumber", []), 16)
    root = "0x" + call(ROCKET_STORAGE, "getBytes32(bytes32)", [keccak256(b"rewards.merkle.root" + n.to_bytes(32, "big"))], ["bytes32"], head)[0].hex()
    res = verify(rf, pf, snap, bn, root)
    os.makedirs("reports", exist_ok=True)
    lines = [f"# Interval {n} (ruleset v{rf['rulesetVersion']})", ""] + [f"- {'PASS' if ok else 'FAIL'} {name}: {d}" for name, ok, d in res]
    open(f"reports/{n}.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return all(ok for _, ok, _ in res)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else latest()
    main(n)
