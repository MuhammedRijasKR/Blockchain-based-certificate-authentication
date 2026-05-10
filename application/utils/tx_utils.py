"""Helpers for sending blockchain transactions and waiting on the receipt.

Without ``wait_for_transaction_receipt`` a reverted transaction silently
appears successful in the UI. ``send_tx`` always waits for the receipt and
raises on a non-1 status, surfacing the on-chain ``require`` message when
possible.
"""

from connection import w3


def send_tx(fn_call, from_addr, gas=None, timeout=120):
    """Submit a contract function call and wait for the receipt.

    Returns the receipt on success. Raises ``RuntimeError`` if the tx reverted.
    """
    tx_kwargs = {"from": from_addr}
    if gas is not None:
        tx_kwargs["gas"] = gas
    tx_hash = fn_call.transact(tx_kwargs)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    if receipt.status != 1:
        raise RuntimeError(f"Transaction reverted (tx_hash={tx_hash.hex()})")
    return receipt


def call_with_revert_message(fn_call, from_addr):
    """Re-run a transact as a ``call`` to surface the Solidity revert reason.

    Useful in ``except`` branches where the user-facing error wasn't clear.
    """
    try:
        fn_call.call({"from": from_addr})
    except Exception as exc:  # pragma: no cover - diagnostic helper
        return str(exc)
    return ""
