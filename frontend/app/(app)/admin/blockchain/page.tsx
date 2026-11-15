"use client";

import { useMemo, useState } from "react";
import { RequireAdmin } from "@/components/require-admin";
import {
  Badge,
  Card,
  DataTable,
  ErrorNote,
  Modal,
  SideBadge,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { MockBlockchainProof, MockProofLink, MockVerifyResult } from "@/lib/types";

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const handle = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      // clipboard may be blocked; nothing fatal
    }
  };
  return (
    <button
      type="button"
      className="copy mono text-[11px] text-mute hover:text-text"
      onClick={handle}
      title={copied ? "Copied" : "Copy"}
    >
      {copied ? "copied" : value}
    </button>
  );
}

function ProofEventBadge({ event_type }: { event_type: string }) {
  const tone =
    event_type === "ORDER_FLAGGED_DEMO"
      ? "warn"
      : event_type === "ORDER_FLAGGED"
        ? "alert"
        : event_type === "ORDER_BLOCKED"
          ? "critical"
          : event_type === "TRADE_EXECUTED"
            ? "gain"
            : "neutral";
  return <Badge tone={tone}>{event_type}</Badge>;
}

function ProofStatusBadge({ status }: { status: string }) {
  const tone =
    status === "mock"
      ? "warn"
      : status === "anchored"
        ? "gain"
        : status === "verification_failed"
          ? "loss"
          : "neutral";
  return (
    <Badge tone={tone}>
      {status === "mock" ? "MOCK" : status}
      {status === "mock" ? " (DEMO)" : ""}
    </Badge>
  );
}

function ProofVerifyStatus({ verified }: { verified: boolean }) {
  return verified ? (
    <Badge tone="gain">VERIFIED (MOCK)</Badge>
  ) : (
    <Badge tone="loss">VERIFICATION FAILED</Badge>
  );
}

function HashChip({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-mute">{label}</span>
      <CopyButton value={value} />
    </div>
  );
}

interface ProofDetailTrade {
  order_id: string | null;
  order_type: string | null;
  execution_id: string | null;
  instrument_id: string | null;
  instrument_symbol: string | null;
  instrument_name: string | null;
  side: string | null;
  quantity: number | null;
  executed_price: number | null;
  executed_quantity: number | null;
  risk_status: string | null;
  security_note: string | null;
  mock: boolean;
}

function ProofLinkButton({
  proofId,
  label,
}: {
  proofId: string;
  label: string;
}) {
  return (
    <a
      href={`/admin/blockchain?proof=${proofId}`}
      className="btn-ghost btn-xs"
    >
      {label}
    </a>
  );
}

function BlockchainContent() {
  const proofs = useApi<{ items: MockBlockchainProof[]; total: number; mock: boolean; network: string }>(
    "/blockchain/proofs?limit=200",
  );
  const [detail, setDetail] = useState<MockBlockchainProof | null>(null);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<MockVerifyResult | null>(null);
  const [linkTrade, setLinkTrade] = useState<MockProofLink | null>(null);
  const [demo, setDemo] = useState<{ key: string; enabled: boolean; mock: boolean; network: string; message?: string; updated_by?: string | null; updated_at?: string | null } | null>(null);
  const [toggleBusy, setToggleBusy] = useState(false);

  const loadDemo = () => {
    api<typeof demo>("/blockchain/demo-toggle").then((d) => setDemo(d)).catch(() => setDemo(null));
  };
  const setDemoEnabled = async (enabled: boolean) => {
    setToggleBusy(true);
    try {
      await api<typeof demo>("/blockchain/demo-toggle", {
        method: "POST",
        body: { enabled },
      });
      loadDemo();
      proofs.reload();
    } finally {
      setToggleBusy(false);
    }
  };

  const openDetail = (proof: MockBlockchainProof) => {
    setDetail(proof);
    setVerifyResult(null);
    setLinkTrade(null);
  };

  const verify = async (proofId: string) => {
    setVerifying(proofId);
    try {
      const result = await api<MockVerifyResult>(`/blockchain/proofs/${proofId}/verify`);
      setVerifyResult(result);
    } finally {
      setVerifying(null);
    }
  };

  const fetchLink = async (proofId: string) => {
    try {
      const link = await api<MockProofLink>(`/blockchain/proofs/${proofId}/link`);
      setLinkTrade(link);
    } catch {
      setLinkTrade(null);
    }
  };

  const columns: Column<MockBlockchainProof>[] = [
    {
      key: "event_type",
      header: "Event type",
      render: (row) => <ProofEventBadge event_type={row.event_type} />,
    },
    {
      key: "client",
      header: "Client / user",
      render: (row) => {
        if (!row.order_id) return <span className="text-xs text-mute">--</span>;
        return <span className="font-mono text-xs">{row.reference_id}</span>;
      },
    },
    {
      key: "instrument",
      header: "Instrument",
      render: (row) => {
        if (!row.instrument_id) return <span className="text-xs text-mute">--</span>;
        return <span className="font-mono text-xs">{row.instrument_id}</span>;
      },
    },
    {
      key: "side",
      header: "Side",
      render: (row) => {
        if (!row.side) return <span className="text-xs text-mute">--</span>;
        return <SideBadge side={row.side} />;
      },
    },
    {
      key: "quantity",
      header: "Quantity",
      render: (row) => {
        if (row.quantity == null) return <span className="text-xs text-mute">--</span>;
        return <span className="num text-xs">{row.quantity}</span>;
      },
    },
    {
      key: "reference",
      header: "Order / reference ID",
      render: (row) => (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-xs">{row.reference_id}</span>
          {row.order_id ? (
            <span className="text-[11px] text-mute">order {row.order_id}</span>
          ) : (
            <span className="text-[11px] text-mute">no linked order</span>
          )}
        </div>
      ),
    },
    {
      key: "record_hash",
      header: "Record hash",
      render: (row) => (
        <div className="proof-hash">
          <HashChip label="record_hash (SHA-256)" value={row.record_hash} />
        </div>
      ),
    },
    {
      key: "transaction_hash",
      header: "Mock tx hash",
      render: (row) => (
        <div className="proof-hash">
          <HashChip label="transaction_hash (mock)" value={row.transaction_hash} />
        </div>
      ),
    },
    {
      key: "block",
      header: "Mock block #",
      render: (row) => <span className="num text-xs">{row.block_number}</span>,
    },
    {
      key: "network",
      header: "Network",
      render: (row) => (
        <span className="text-xs text-mute" title={row.network}>
          {row.network}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (row) => <ProofStatusBadge status={row.blockchain_status} />,
    },
    {
      key: "verify",
      header: "Verification",
      align: "right",
      render: (row) => {
        const existing = verifyResult && verifyResult.record_hash === row.record_hash;
        const result = (
          <>
            {existing ? (
              <ProofVerifyStatus verified={verifyResult!.verified} />
            ) : null}
            {existing && verifyResult && (
              <span className="text-[11px] text-mute mt-1 block">
                recomputed record_hash: <CopyButton value={verifyResult.recomputed_record_hash} />
              </span>
            )}
          </>
        );
        return (
          <div className="flex items-center justify-end gap-2">
            {result}
            <button
              type="button"
              className="btn-ghost btn-xs"
              disabled={verifying === row.proof_id}
              onClick={() => verify(row.proof_id)}
            >
              {verifying === row.proof_id ? "Verifying…" : "Verify"}
            </button>
          </div>
        );
      },
    },
    {
      key: "created",
      header: "Created",
      render: (row) => <span className="text-xs text-mute">{dateTime(row.created_at)}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <Card
        title="Blockchain Audit Integrity"
        subtitle="MOCK proof layer for demonstration"
        action={<Badge tone="neutral">MOCK</Badge>}
      >
        <div className="space-y-3">
          <p className="text-sm text-mute">
            This page shows MOCK blockchain proof metadata for critical TradeShield
            events. It is NOT a real blockchain, does NOT contain real transactions,
            and does NOT replace PostgreSQL, which remains the system of record.
          </p>

          <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
            <p className="text-sm font-semibold">What these hashes are</p>
            <ul className="mt-2 space-y-1.5 text-sm text-mute">
              <li>
                <strong className="text-text">record_hash</strong> — a locally generated SHA-256 digest of the proof&apos;s own canonical metadata
                (`entity_type:reference_id:event_type:created_at`). It is a tamper-evident fingerprint of the TradeShield event, not a chain transaction.
              </li>
              <li>
                <strong className="text-text">transaction_hash</strong> — a locally generated SHA-256 digest of a mock string
                (`TradeShield Local Mock Chain:tx:&lt;proof_id&gt;`). It looks like a Bitcoin/Ethereum tx hash but is not one.
              </li>
              <li>
                <strong className="text-text">block_number</strong> — a deterministic mock integer in a realistic-looking range.
              </li>
              <li>
                <strong className="text-text">contract_address</strong> — a deterministic mock 0x... address from a fixed mock salt.
              </li>
              <li>
                Verification recomputes the stored record_hash from the proof metadata and compares it to the stored value.
                A match means the stored row has not changed — not that anything is on a real chain.
              </li>
            </ul>
          </div>

          <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
            <p className="text-sm font-semibold">How the hashes are generated</p>
            <p className="mt-1 text-sm text-mute">
              All three values are computed locally with SHA-256 from TradeShield event metadata using Python&apos;s{" "}
              <code className="font-mono text-xs">hashlib.sha256</code> and PostgreSQL&apos;s{" "}
              <code className="font-mono text-xs">digest(..., &apos;sha256&apos;)</code>. Nothing is submitted to any chain, no Web3
              library is used, and no wallet or private key exists.
            </p>
          </div>

          <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
            <p className="text-sm font-semibold">Demo trade flagging (MOCK)</p>
            <p className="mt-1 text-sm text-mute">
              When enabled, trades from <span className="font-mono text-xs">client@tradeshield.dev</span> are executed
              normally, marked FLAGGED with a demo note, and a matching MOCK proof is saved that identifies the actual
              instrument, side and quantity traded.
            </p>

            <div className="mt-4 flex items-center gap-3">
              <button
                type="button"
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${demo?.enabled ? "bg-gain" : "bg-ink-700"} ${toggleBusy ? "opacity-50 cursor-wait" : ""}`}
                disabled={toggleBusy}
                onClick={() => setDemoEnabled(!demo?.enabled)}
                aria-pressed={demo?.enabled}
                aria-label={demo?.enabled ? "Disable demo trade flagging" : "Enable demo trade flagging"}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${demo?.enabled ? "translate-x-6" : "translate-x-1"}`}
                />
              </button>
              <span className="text-sm font-medium">{demo?.enabled ? "ON" : "OFF"}</span>
            </div>
            {demo?.message && <p className="mt-2 text-xs text-mute">{demo.message}</p>}
            {demo?.updated_at && (
              <p className="text-[11px] text-mute">updated {new Date(demo.updated_at).toLocaleString()}</p>
            )}
          </div>

          <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
            <p className="text-sm font-semibold">How to demo this page</p>
            <ol className="mt-2 space-y-1.5 text-sm text-mute">
              <li>Enable demo trade flagging above (if not already on).</li>
              <li>Sign in as <span className="font-mono text-xs">client@tradeshield.dev</span> and place a BUY or SELL order.</li>
              <li>The order executes, is marked FLAGGED (DEMO), and a proof appears below.</li>
              <li>Click any proof row to open the detail modal and see the full hashes, the trade it anchors, and run Verify.</li>
              <li>From the admin Blocked & flagged orders page, each ORDER_FLAGGED_DEMO event links back to its proof.</li>
            </ol>
          </div>
        </div>
      </Card>

      {proofs.error ? (
        <ErrorNote message={proofs.error.message} onRetry={proofs.reload} />
      ) : proofs.loading ? (
        <div className="text-sm text-mute">Loading proofs…</div>
      ) : proofs.data && proofs.data.items.length > 0 ? (
        <DataTable
          columns={columns}
          rows={proofs.data.items}
          loading={proofs.loading}
          rowKey={(row) => row.proof_id}
          onRowClick={(row) => openDetail(row)}
          emptyTitle="No proof records yet"
          emptyHint="Enable demo trade flagging and place a trade, then refresh."
        />
      ) : (
        <div className="text-sm text-mute">No proof records found.</div>
      )}

      {detail && (
        <ProofDetailModal
          proof={detail}
          open
          onClose={() => setDetail(null)}
          verifying={verifying === detail.proof_id}
          verifyResult={verifyResult}
          onVerify={() => verify(detail.proof_id)}
          linkTrade={linkTrade}
          onFetchLink={() => fetchLink(detail.proof_id)}
        />
      )}

      {linkTrade && !detail && (
        <ProofLinkModal
          link={linkTrade}
          open
          onClose={() => setLinkTrade(null)}
        />
      )}
    </div>
  );
}

function ProofDetailModal({
  proof,
  open,
  onClose,
  verifying,
  verifyResult,
  onVerify,
  linkTrade,
  onFetchLink,
}: {
  proof: MockBlockchainProof;
  open: boolean;
  onClose: () => void;
  verifying: boolean;
  verifyResult: MockVerifyResult | null;
  onVerify: () => void;
  linkTrade: MockProofLink | null;
  onFetchLink: () => void;
}) {
  return (
    <Modal
      open={open}
      title={`Proof ${proof.proof_id}`}
      subtitle={`${proof.entity_type} · ${proof.event_type} · MOCK`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onFetchLink}>
            {linkTrade ? "Refresh linked trade" : "Show linked trade"}
          </button>
          <button type="button" className="btn-ghost" onClick={onVerify} disabled={verifying}>
            {verifying ? "Verifying…" : "Verify"}
          </button>
          <button type="button" className="btn-primary" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-mute">
          This is a MOCK proof. The record_hash and transaction_hash below are locally
          generated SHA-256 digests of TradeShield event metadata — they are not real
          on-chain transactions and no blockchain is involved.
        </p>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="label">Proof ID</dt>
            <dd className="font-mono text-xs text-mute">{proof.proof_id}</dd>
          </div>
          <div>
            <dt className="label">Reference ID</dt>
            <dd className="font-mono text-xs text-mute">{proof.reference_id}</dd>
          </div>
          <div>
            <dt className="label">Entity type</dt>
            <dd className="text-xs text-mute">{proof.entity_type}</dd>
          </div>
          <div>
            <dt className="label">Event type</dt>
            <dd className="text-xs text-mute">{proof.event_type}</dd>
          </div>
          <div>
            <dt className="label">Network (MOCK)</dt>
            <dd className="font-mono text-xs text-mute">{proof.network}</dd>
          </div>
          <div>
            <dt className="label">Contract address (MOCK)</dt>
            <dd className="font-mono text-xs text-mute">{proof.contract_address}</dd>
          </div>
          <div>
            <dt className="label">Mock block number</dt>
            <dd className="num text-xs">{proof.block_number}</dd>
          </div>
          <div>
            <dt className="label">Status</dt>
            <dd className="text-xs text-mute">
              <ProofStatusBadge status={proof.blockchain_status} />
            </dd>
          </div>
        </dl>

        <div className="rounded-xl border border-edge/70 bg-ink-900/40 p-4 space-y-3">
          <p className="text-sm font-semibold">Record hash (SHA-256 of canonical metadata)</p>
          <HashChip
            label="record_hash (64-char hex)"
            value={proof.record_hash}
          />
          <p className="text-xs text-mute">
            Canonical input: <code className="font-mono text-xs">{proof.entity_type}:{proof.reference_id}:{proof.event_type}:{proof.created_at}</code>
          </p>
        </div>

        <div className="rounded-xl border border-edge/70 bg-ink-900/40 p-4 space-y-3">
          <p className="text-sm font-semibold">Mock transaction hash</p>
          <HashChip
            label="transaction_hash (64-char hex, mock)"
            value={proof.transaction_hash}
          />
          <p className="text-xs text-mute">
            Mock canonical input: <code className="font-mono text-xs">{proof.network}:tx:{proof.proof_id}</code>
          </p>
        </div>

        {linkTrade && (
          <dl className="grid grid-cols-2 gap-4 text-sm rounded-xl border border-edge/70 bg-ink-900/40 p-4">
            <dt className="label">Linked trade</dt>
            <dd className="text-xs text-mute">
              {linkTrade.trade.order_id ? (
                <>
                  Order <span className="font-mono text-xs">{linkTrade.trade.order_id}</span>
                  {" "}·{" "}
                  <a
                    href={`/admin/orders/${linkTrade.trade.order_id}`}
                    className="text-brand-soft hover:underline text-xs"
                  >
                    View order
                  </a>
                </>
              ) : (
                <span className="text-mute">no linked order</span>
              )}
            </dd>
            {linkTrade.trade.instrument_symbol && (
              <div>
                <dt className="label">Instrument</dt>
                <dd className="text-xs text-mute">
                  <span className="font-semibold">{linkTrade.trade.instrument_symbol}</span>{" "}
                  <span className="text-mute">({linkTrade.trade.instrument_name})</span>
                </dd>
              </div>
            )}
            {linkTrade.trade.side && (
              <div>
                <dt className="label">Side</dt>
                <dd className="text-xs">
                  <SideBadge side={linkTrade.trade.side} />
                </dd>
              </div>
            )}
            {linkTrade.trade.quantity != null && (
              <div>
                <dt className="label">Quantity</dt>
                <dd className="num text-xs">{linkTrade.trade.quantity}</dd>
              </div>
            )}
            {linkTrade.trade.order_type && (
              <div>
                <dt className="label">Order type</dt>
                <dd className="text-xs text-mute">{linkTrade.trade.order_type}</dd>
              </div>
            )}
            {linkTrade.trade.risk_status && (
              <div>
                <dt className="label">Risk status</dt>
                <dd className="text-xs text-mute">{linkTrade.trade.risk_status}</dd>
              </div>
            )}
            {linkTrade.trade.security_note && (
              <div className="col-span-2">
                <dt className="label">Demo note</dt>
                <dd className="text-xs text-mute">{linkTrade.trade.security_note}</dd>
              </div>
            )}
          </dl>
        )}

        {verifyResult && (
          <div className="rounded-xl border border-edge/70 bg-ink-900/40 p-4 space-y-3">
            <p className="text-sm font-semibold">Verification result (MOCK)</p>
            <div className="flex items-center gap-2">
              <ProofVerifyStatus verified={verifyResult.verified} />
              <span className="text-xs text-mute">mock verification</span>
            </div>
            <dl className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <dt className="text-mute">Stored record_hash</dt>
                <dd className="font-mono"><CopyButton value={verifyResult.record_hash} /></dd>
              </div>
              <div>
                <dt className="text-mute">Recomputed record_hash</dt>
                <dd className="font-mono"><CopyButton value={verifyResult.recomputed_record_hash} /></dd>
              </div>
              <div>
                <dt className="text-mute">Matched</dt>
                <dd className="text-xs">{verifyResult.verified ? "yes" : "no"}</dd>
              </div>
              <div>
                <dt className="text-mute">Transaction hash</dt>
                <dd className="font-mono"><CopyButton value={verifyResult.transaction_hash} /></dd>
              </div>
            </dl>
          </div>
        )}

        {!linkTrade && proof.order_id && (
          <p className="text-xs text-mute">
            This proof references an order. Click{" "}
            <button type="button" className="text-brand-soft hover:underline text-xs" onClick={onFetchLink}>
              Show linked trade
            </button>{" "}
            to fetch the instrument, side and quantity.
          </p>
        )}
      </div>
    </Modal>
  );
}

function ProofLinkModal({ link, open, onClose }: { link: MockProofLink; open: boolean; onClose: () => void }) {
  return (
    <Modal
      open={open}
      title="Linked trade"
      subtitle={`${link.entity_type} · ${link.event_type} · MOCK`}
      onClose={onClose}
      footer={
        <>
          {link.trade.order_id ? (
            <a
              href={`/admin/orders/${link.trade.order_id}`}
              className="btn-primary"
            >
              View order
            </a>
          ) : null}
          <button type="button" className="btn-ghost" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-mute">
          The trade this MOCK proof is anchored to, fetched live from the orders table.
        </p>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          {link.trade.order_id && (
            <>
              <div>
                <dt className="label">Order ID</dt>
                <dd className="font-mono text-xs text-mute">{link.trade.order_id}</dd>
              </div>
              <div>
                <dt className="label">Order type</dt>
                <dd className="text-xs text-mute">{link.trade.order_type}</dd>
              </div>
              <div>
                <dt className="label">Instrument</dt>
                <dd className="text-xs text-mute">
                  <span className="font-semibold">{link.trade.instrument_symbol}</span>{" "}
                  <span className="text-mute">({link.trade.instrument_name})</span>
                </dd>
              </div>
              <div>
                <dt className="label">Side</dt>
                <dd className="text-xs"><SideBadge side={link.trade.side ?? ""} /></dd>
              </div>
              <div>
                <dt className="label">Quantity</dt>
                <dd className="num text-xs">{link.trade.quantity}</dd>
              </div>
              {link.trade.executed_price != null && (
                <div>
                  <dt className="label">Executed price</dt>
                  <dd className="num text-xs">{money(link.trade.executed_price, 4)}</dd>
                </div>
              )}
              {link.trade.executed_quantity != null && (
                <div>
                  <dt className="label">Executed quantity</dt>
                  <dd className="num text-xs">{link.trade.executed_quantity}</dd>
                </div>
              )}
              <div>
                <dt className="label">Risk status</dt>
                <dd className="text-xs text-mute">{link.trade.risk_status}</dd>
              </div>
              {link.trade.security_note && (
                <div className="col-span-2">
                  <dt className="label">Demo note</dt>
                  <dd className="text-xs text-mute">{link.trade.security_note}</dd>
                </div>
              )}
            </>
          )}
          {!link.trade.order_id && (
            <div className="col-span-2 text-xs text-mute">
              This proof is not linked to a real order (seed or non-trade proof).
            </div>
          )}
        </dl>
      </div>
    </Modal>
  );
}

export default function BlockchainPage() {
  return (
    <RequireAdmin>
      <BlockchainContent />
    </RequireAdmin>
  );
}
