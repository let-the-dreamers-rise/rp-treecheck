"""Rewards Merkle tree, written from merkle-tree-spec.md (RPIP-53 asset)."""
from Crypto.Hash import keccak

NULL = b"\x00" * 32


def keccak256(b: bytes) -> bytes:
    return keccak.new(digest_bits=256, data=b).digest()


def leaf(address: str, network: int, total_rpl: int, total_eth: int) -> bytes:
    a = bytes.fromhex(address[2:])
    assert len(a) == 20
    return keccak256(a + network.to_bytes(32, "big") + total_rpl.to_bytes(32, "big") + total_eth.to_bytes(32, "big"))


def leaf_v1(address: str, network: int, total_rpl: int, sp_eth: int, voter_eth: int) -> bytes:
    """Tree version 1 (ruleset v11): 148-byte leaf with a separate voter-share ETH amount."""
    a = bytes.fromhex(address[2:])
    assert len(a) == 20
    return keccak256(a + network.to_bytes(32, "big") + total_rpl.to_bytes(32, "big")
                     + sp_eth.to_bytes(32, "big") + voter_eth.to_bytes(32, "big"))


def branch(l: bytes, r: bytes) -> bytes:
    if r < l:
        l, r = r, l
    return keccak256(l + r)


def build(leaves):
    """Return list of levels, level[0] = sorted+padded leaves, last = [root]."""
    lv = sorted(leaves)
    n = 1
    while n < len(lv):
        n *= 2
    lv = lv + [NULL] * (n - len(lv))
    levels = [lv]
    while len(lv) > 1:
        lv = [branch(lv[i], lv[i + 1]) for i in range(0, len(lv), 2)]
        levels.append(lv)
    return levels


def proof(levels, leaf_value):
    i = levels[0].index(leaf_value)
    out = []
    for lv in levels[:-1]:
        out.append(lv[i ^ 1])
        i //= 2
    return out


def verify(leaf_value, prf, root):
    h = leaf_value
    for p in prf:
        h = branch(h, p)
    return h == root
