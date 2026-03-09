"""
Merkle Tree utilities for bulk certificate issuance.
Builds a Merkle tree from certificate leaf hashes, generates proofs, and verifies them.
"""
import hashlib
import json
import os

MERKLE_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "merkle_proofs.json")


def compute_leaf(salt, uid, candidate_name, course_name, org_name, grade=""):
    """Compute a leaf hash for a single certificate."""
    data = f"{salt}{uid}{candidate_name}{course_name}{org_name}{grade}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _hash_pair(left, right):
    """Hash two hex strings together in sorted order (canonical)."""
    # Sort to ensure deterministic ordering
    if left <= right:
        combined = left + right
    else:
        combined = right + left
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def build_merkle_tree(leaves):
    """
    Build a Merkle tree from a list of leaf hex hashes.
    Returns the root hash and the full tree layers.
    """
    if not leaves:
        return None, []

    # If odd number of leaves, duplicate the last one
    current_layer = list(leaves)
    tree_layers = [current_layer[:]]

    while len(current_layer) > 1:
        next_layer = []
        for i in range(0, len(current_layer), 2):
            if i + 1 < len(current_layer):
                parent = _hash_pair(current_layer[i], current_layer[i + 1])
            else:
                # Odd leaf: hash with itself
                parent = _hash_pair(current_layer[i], current_layer[i])
            next_layer.append(parent)
        current_layer = next_layer
        tree_layers.append(current_layer[:])

    root = current_layer[0]
    return root, tree_layers


def get_merkle_proof(tree_layers, leaf_index):
    """
    Generate a Merkle proof for a leaf at the given index.
    Returns a list of (sibling_hash, position) tuples.
    position: 'left' or 'right' indicates where the sibling is.
    """
    proof = []
    idx = leaf_index

    for layer in tree_layers[:-1]:  # Skip root layer
        if idx % 2 == 0:
            # Sibling is on the right
            sibling_idx = idx + 1
            if sibling_idx < len(layer):
                proof.append(layer[sibling_idx])
            else:
                proof.append(layer[idx])  # Odd: duplicate self
        else:
            # Sibling is on the left
            proof.append(layer[idx - 1])
        idx = idx // 2

    return proof


def verify_merkle_proof(leaf_hash, proof, root):
    """
    Verify a Merkle proof for a given leaf hash against the root.
    """
    computed = leaf_hash
    for sibling in proof:
        computed = _hash_pair(computed, sibling)
    return computed == root


def save_batch_proofs(batch_id, certificates, tree_layers, root):
    """
    Save Merkle proofs for all certificates in a batch to a local JSON file.
    Each certificate entry includes: certificate_id, leaf_hash, proof, and cert metadata.
    """
    store = _load_store()

    batch_data = {
        "root": root,
        "certificate_count": len(certificates),
        "certificates": {}
    }

    for i, cert in enumerate(certificates):
        proof = get_merkle_proof(tree_layers, i)
        batch_data["certificates"][cert["certificate_id"]] = {
            "leaf_hash": cert["leaf_hash"],
            "proof": proof,
            "uid": cert["uid"],
            "candidate_name": cert["candidate_name"],
            "course_name": cert["course_name"],
            "org_name": cert["org_name"],
            "salt": cert["salt"],
            "grade": cert.get("grade", ""),
            "ipfs_hash": cert.get("ipfs_hash", ""),
            "leaf_index": i
        }

    store[str(batch_id)] = batch_data
    _save_store(store)


def get_certificate_proof(batch_id, certificate_id):
    """
    Retrieve Merkle proof and metadata for a specific certificate from a batch.
    """
    store = _load_store()
    batch = store.get(str(batch_id))
    if batch is None:
        return None
    return batch["certificates"].get(certificate_id)


def get_batch_root(batch_id):
    """Get the stored Merkle root for a batch."""
    store = _load_store()
    batch = store.get(str(batch_id))
    if batch:
        return batch["root"]
    return None


def find_certificate_batch(certificate_id):
    """
    Find which batch a certificate belongs to.
    Returns (batch_id, cert_data) or (None, None).
    """
    store = _load_store()
    for batch_id, batch_data in store.items():
        if certificate_id in batch_data["certificates"]:
            return batch_id, batch_data["certificates"][certificate_id]
    return None, None


def _load_store():
    if os.path.exists(MERKLE_STORE_PATH):
        with open(MERKLE_STORE_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_store(store):
    with open(MERKLE_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)
