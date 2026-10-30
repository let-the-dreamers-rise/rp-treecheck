"""Mutation tests: every single-field corruption of a real published tree must be caught."""
import copy, json, os, random, urllib.request
import pytest
from rptc.filecheck import check_rewards_file
from rptc.rpl import log2, ln, ETH

RAW = "https://raw.githubusercontent.com/rocket-pool/rewards-trees/main/mainnet/rp-rewards-mainnet-{}.json"


def load(n):
    path = os.path.join(os.path.dirname(__file__), "..", "cache", f"rp-rewards-mainnet-{n}.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(RAW.format(n), path)
    return json.load(open(path))


def failed(rf):
    return [name for name, ok, _ in check_rewards_file(rf) if not ok]


@pytest.fixture(scope="module")
def rf54():
    return load(54)


def test_published_tree_passes_tree_checks(rf54):
    assert failed(rf54) == ["SP split conserves ETH (staker + NO + voter + pDAO == total)"]  # F3, known 41 wei


FIELDS = ["collateralRpl", "oracleDaoRpl", "smoothingPoolEth", "voterShareEth"]


@pytest.mark.parametrize("seed", range(40))
def test_single_amount_mutation_is_caught(rf54, seed):
    rnd = random.Random(seed)
    rf = copy.deepcopy(rf54)
    addr = rnd.choice(list(rf["nodeRewards"]))
    field = rnd.choice(FIELDS)
    rf["nodeRewards"][addr][field] = str(int(rf["nodeRewards"][addr][field]) + rnd.choice([1, 10 ** 9, 10 ** 18]))
    assert "merkle root reproduces" in failed(rf)


def test_moving_wei_between_nodes_is_caught(rf54):
    # sums stay equal, so only the Merkle checks can catch it
    rf = copy.deepcopy(rf54)
    a, b = [k for k, v in rf["nodeRewards"].items() if int(v["smoothingPoolEth"]) > 0][:2]
    rf["nodeRewards"][a]["smoothingPoolEth"] = str(int(rf["nodeRewards"][a]["smoothingPoolEth"]) + 1)
    rf["nodeRewards"][b]["smoothingPoolEth"] = str(int(rf["nodeRewards"][b]["smoothingPoolEth"]) - 1)
    f = failed(rf)
    assert "merkle root reproduces" in f and "every published proof verifies" in f


def test_dropped_claimer_is_caught(rf54):
    rf = copy.deepcopy(rf54)
    rf["nodeRewards"].pop(next(iter(rf["nodeRewards"])))
    assert "merkle root reproduces" in failed(rf)


def test_swapped_proof_is_caught(rf54):
    rf = copy.deepcopy(rf54)
    a, b = list(rf["nodeRewards"])[:2]
    rf["nodeRewards"][a]["merkleProof"], rf["nodeRewards"][b]["merkleProof"] = rf["nodeRewards"][b]["merkleProof"], rf["nodeRewards"][a]["merkleProof"]
    assert "every published proof verifies" in failed(rf)


def test_v10_leaf_format_still_reproduces():
    assert failed(load(45)) == []


def test_log2_ln_spec_values():
    assert log2(ETH) == 0
    assert log2(32 * ETH) == 5 * ETH
    assert abs(ln(2 * ETH) - 693147180559945309) < 10 ** 6
