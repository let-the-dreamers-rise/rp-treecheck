"""Minimal JSON-RPC + Multicall3 client for historical (archive) reads."""
import json, os, time, urllib.request
from eth_abi import encode, decode
from .merkle import keccak256

RPC = os.environ.get("RPTC_RPC", "https://eth.drpc.org")
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
ROCKET_STORAGE = "0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46"


def rpc(method, params, retries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(RPC, body, {"content-type": "application/json", "user-agent": "rp-treecheck"})
            r = json.load(urllib.request.urlopen(req, timeout=90))
            if "error" in r:
                raise RuntimeError(r["error"])
            return r["result"]
        except Exception as e:  # rate limits / transient errors
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def selector(sig):
    return keccak256(sig.encode())[:4]


def calldata(sig, *args):
    types = sig[sig.index("(") + 1:-1]
    types = [t for t in types.split(",") if t]
    return selector(sig) + (encode(types, list(args)) if types else b"")


def call(to, sig, args, out, block):
    data = "0x" + calldata(sig, *args).hex()
    r = rpc("eth_call", [{"to": to, "data": data}, hex(block)])
    return decode(out, bytes.fromhex(r[2:]))


def multicall(calls, block, batch=400):
    """calls: list of (to, sig, args, out_types). Returns decoded tuples (None on revert)."""
    res = []
    for k in range(0, len(calls), batch):
        chunk = calls[k:k + batch]
        enc = [(c[0], True, calldata(c[1], *c[2])) for c in chunk]
        data = selector("aggregate3((address,bool,bytes)[])") + encode(["(address,bool,bytes)[]"], [enc])
        r = rpc("eth_call", [{"to": MULTICALL3, "data": "0x" + data.hex()}, hex(block)])
        (rets,) = decode(["(bool,bytes)[]"], bytes.fromhex(r[2:]))
        for (ok, b), c in zip(rets, chunk):
            res.append(decode(c[3], b) if ok and len(b) else None)
    return res


def contract(name, block):
    key = keccak256(b"contract.address" + name.encode())
    (a,) = call(ROCKET_STORAGE, "getAddress(bytes32)", [key], ["address"], block)
    return a
