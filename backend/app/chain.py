"""
TradeShield * real blockchain anchor layer.

Connects to the local Hardhat node and anchors audit proofs to the
TradeShieldAudit smart contract.  Everything here is best-effort:
when the node is unreachable or any call fails, the caller falls
back to the existing mock layer without breaking anything.

Usage
-----
    from .chain import anchor_proof_on_chain, chain_status

    result = anchor_proof_on_chain(
        event_ref="exec:some-uuid",
        event_type="TRADE_EXECUTED",
        record_hash_hex="abcdef1234...",   # 64-char hex
    )
    # result is None when the node is offline / not configured.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ABI -- only the functions we call (anchor + read).  Keeping it minimal
# means we do not need to ship the full Hardhat compilation artefact.
# ---------------------------------------------------------------------------

_ABI = [
    {
        "inputs": [
            {"internalType": "string",  "name": "_eventRef",   "type": "string"},
            {"internalType": "string",  "name": "_eventType",  "type": "string"},
            {"internalType": "bytes32", "name": "_recordHash", "type": "bytes32"},
        ],
        "name": "anchorProof",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "_eventRef", "type": "string"}],
        "name": "getProof",
        "outputs": [
            {"internalType": "bytes32", "name": "recordHash",  "type": "bytes32"},
            {"internalType": "uint256", "name": "anchoredAt",  "type": "uint256"},
            {"internalType": "bool",    "name": "exists",      "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "string",  "name": "_eventRef",   "type": "string"},
            {"internalType": "bytes32", "name": "_recordHash", "type": "bytes32"},
        ],
        "name": "verifyProof",
        "outputs": [
            {"internalType": "bool", "name": "matches", "type": "bool"},
            {"internalType": "bool", "name": "exists",  "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalProofs",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class AnchorResult(TypedDict):
    tx_hash: str        # 0x... transaction hash
    block_number: int
    contract_address: str
    network: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_web3():
    """Import web3; return None when it is not installed."""
    try:
        from web3 import Web3  # type: ignore
        return Web3
    except ImportError:
        return None


def _get_config() -> tuple[str, str, str] | None:
    """
    Read (node_url, private_key, contract_address) from env / deployment file.

    Returns None when blockchain is not configured (optional feature).
    """
    node_url = os.environ.get("BLOCKCHAIN_NODE_URL", "").strip()
    private_key = os.environ.get("BLOCKCHAIN_PRIVATE_KEY", "").strip()
    contract_address = os.environ.get("BLOCKCHAIN_CONTRACT_ADDRESS", "").strip()

    # If the contract address is not set in env, try to read from the
    # deployment artefact written by `hardhat run scripts/deploy.js`.
    if not contract_address:
        contract_address = _read_deployment_address()

    if not node_url or not private_key or not contract_address:
        return None
    return node_url, private_key, contract_address


def _read_deployment_address() -> str:
    """
    Read the contract address from blockchain/deployment.json if it exists.
    The deploy script writes this file so the backend picks it up automatically.
    """
    # backend/app/chain.py -> parents[0]=app, [1]=backend, [2]=repo root
    root = Path(__file__).resolve().parents[2]
    deployment_file = root / "blockchain" / "deployment.json"
    if not deployment_file.exists():
        return ""
    try:
        data = json.loads(deployment_file.read_text())
        return data.get("address", "")
    except Exception:
        return ""


def _build_contract(Web3, node_url: str, private_key: str, contract_address: str):
    """
    Build a web3 contract instance.  Returns (w3, contract, account) or raises.
    """
    w3 = Web3(Web3.HTTPProvider(node_url, request_kwargs={"timeout": 5}))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to node at {node_url}")

    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=_ABI,
    )
    return w3, contract, account


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def anchor_proof_on_chain(
    *,
    event_ref: str,
    event_type: str,
    record_hash_hex: str,
) -> AnchorResult | None:
    """
    Anchor a proof on the TradeShieldAudit smart contract.

    Parameters
    ----------
    event_ref       : unique reference string (≤ 64 chars), e.g. "exec:<uuid>"
    event_type      : categorical label (≤ 64 chars), e.g. "TRADE_EXECUTED"
    record_hash_hex : 64-character hex SHA-256 digest of the canonical payload

    Returns
    -------
    AnchorResult dict on success, None when blockchain is not configured or
    the call fails (caller should fall back to mock).
    """
    Web3 = _load_web3()
    if Web3 is None:
        logger.debug("chain: web3 not installed; skipping on-chain anchor")
        return None

    cfg = _get_config()
    if cfg is None:
        logger.debug("chain: blockchain not configured; skipping on-chain anchor")
        return None

    node_url, private_key, contract_address = cfg

    try:
        w3, contract, account = _build_contract(Web3, node_url, private_key, contract_address)

        # Convert 64-char hex string to bytes32
        record_hash_bytes = bytes.fromhex(record_hash_hex)

        # Build and send the transaction
        tx = contract.functions.anchorProof(
            event_ref,
            event_type,
            record_hash_bytes,
        ).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

        chain_id = w3.eth.chain_id
        return AnchorResult(
            tx_hash=receipt.transactionHash.hex(),
            block_number=receipt.blockNumber,
            contract_address=contract_address,
            network=f"hardhat-local:{chain_id}",
        )

    except Exception as exc:
        logger.warning("chain: on-chain anchor failed (%s); falling back to mock", exc)
        return None


def verify_proof_on_chain(
    *,
    event_ref: str,
    record_hash_hex: str,
) -> dict | None:
    """
    Call verifyProof() on-chain.

    Returns dict with matches/exists/anchored_at, or None on error.
    """
    Web3 = _load_web3()
    if Web3 is None:
        return None

    cfg = _get_config()
    if cfg is None:
        return None

    node_url, private_key, contract_address = cfg

    try:
        w3, contract, _ = _build_contract(Web3, node_url, private_key, contract_address)
        record_hash_bytes = bytes.fromhex(record_hash_hex)
        matches, exists = contract.functions.verifyProof(event_ref, record_hash_bytes).call()
        _, anchored_at, _ = contract.functions.getProof(event_ref).call()
        return {"matches": matches, "exists": exists, "anchored_at": anchored_at}
    except Exception as exc:
        logger.warning("chain: on-chain verify failed (%s)", exc)
        return None


def chain_status() -> dict:
    """
    Returns connectivity status for the health endpoint.

    Always returns a dict; never raises.
    """
    Web3 = _load_web3()
    if Web3 is None:
        return {"available": False, "reason": "web3 not installed"}

    cfg = _get_config()
    if cfg is None:
        return {"available": False, "reason": "blockchain not configured"}

    node_url, _, contract_address = cfg
    try:
        w3 = Web3(Web3.HTTPProvider(node_url, request_kwargs={"timeout": 3}))
        if not w3.is_connected():
            return {"available": False, "reason": "node unreachable", "node": node_url}
        total = None
        try:
            from web3 import Web3 as _W3  # type: ignore
            contract = w3.eth.contract(
                address=_W3.to_checksum_address(contract_address), abi=_ABI
            )
            total = contract.functions.totalProofs().call()
        except Exception:
            pass
        return {
            "available": True,
            "node": node_url,
            "chain_id": w3.eth.chain_id,
            "contract_address": contract_address,
            "total_on_chain_proofs": total,
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}

