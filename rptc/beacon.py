"""Beacon API reads. Only the head state is needed for validator activation/exit epochs:
both are write-once, so head-state values decide eligibility at any earlier target slot."""
import json, os, time, urllib.request

BN = os.environ.get("RPTC_BEACON", "https://ethereum-beacon-api.publicnode.com")


def _req(path, body=None, retries=6):
    for i in range(retries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(BN + path, data, {"content-type": "application/json", "user-agent": "rp-treecheck"})
            return json.load(urllib.request.urlopen(req, timeout=120))
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def validators(pubkeys, state="head", batch=200):
    out = {}
    pubkeys = ["0x" + p.removeprefix("0x") for p in pubkeys]
    for k in range(0, len(pubkeys), batch):
        r = _req(f"/eth/v1/beacon/states/{state}/validators", {"ids": pubkeys[k:k + batch]})
        for v in r["data"]:
            val = v["validator"]
            out[val["pubkey"][2:]] = {"index": int(v["index"]), "activation_epoch": int(val["activation_epoch"]),
                                      "exit_epoch": int(val["exit_epoch"]), "withdrawable_epoch": int(val["withdrawable_epoch"]),
                                      "status": v["status"]}
    return out


def block(slot):
    return _req(f"/eth/v2/beacon/blocks/{slot}")
