"use client";

import { useMemo, useEffect, useState } from "react";
import { RequireAdmin } from "@/components/require-admin";
import { Badge, Card, DataTable, ErrorNote, type Column } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { MockBlockchainProof, MockVerifyResult } from "@/lib/types";

interface DemoToggle {
  key: string;
  enabled: boolean;
  mock: boolean;
  network: string;
  message?: string;
  updated_by?: string | null;
  updated_at?: string | null;
}

function ProofVerifyStatus({ verified }: { verified: boolean }) {
  return verified
    ? <Badge tone="gain">MOCK verified</Badge>
    : <Badge tone="loss">MOCK mismatch</Badge>;
}

function EventBadge({ event_type }: { event_type: string }) {
  const tone =
    event_type === "ORDER_FLAGGED_DEMO"
      ? "warn"
      : event_type === "ORDER_BLOCKED"
        ? "critical"
        : event_type === "TRADE_EXECUTED"
          ? "gain"
          : "neutral";
  return <Badge tone={tone}>{event_type}</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "anchored"
      ? "gain"
      : status === "verification_failed"
        ? "loss"
        : status === "mock"
          ? "warn"
          : "neutral";
  return (
    <Badge tone={tone}>
      {status}
      {status === "mock" ? " (DEMO)" : ""}
    </Badge>
  );
}

function DemoTogglePanel({
  demo,
  busy,
  onLoad,
  onEnable,
  onDisable,
}: {
  demo: DemoToggle | null;
  busy: boolean;
  onLoad: () => void;
  onEnable: () => void;
  onDisable: () => void;
}) {
  if (!demo) {
    return (
      <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
        <p className="text-sm font-semibold">Demo trade flagging (MOCK)</p>
        <p className="mt-1 text-sm text-mute">
          Loading demo toggle state…
        </p>
        <button
          type="button"
          className="btn-ghost btn-xs mt-2"
          onClick={onLoad}
        >
          Reload state
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
      <p className="text-sm font-semibold">Demo trade flagging (MOCK)</p>
      <p className="mt-1 text-sm text-mute">
        When enabled, trades from <span className="font-mono text-xs">client@tradeshield.dev</span>{" "}
        are flagged for demonstration.
      </p>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            demo.enabled ? "bg-gain" : "bg-ink-700"
          } ${busy ? "opacity-50 cursor-wait" : ""}`}
          disabled={busy}
          onClick={demo.enabled ? onDisable : onEnable}
          aria-pressed={demo.enabled}
          aria-label={demo.enabled ? "Disable demo trade flagging" : "Enable demo trade flagging"}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              demo.enabled ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <span className="text-sm font-medium">
          {demo.enabled ? "ON" : "OFF"}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 items-center">
        {demo.message && (
          <span className="text-xs text-mute">{demo.message}</span>
        )}
        {demo.updated_at && (
          <span className="text-[11px] text-mute">
            updated {new Date(demo.updated_at).toLocaleString()}
          </span>
        )}
      </div>
    </div>
  );
}

function BlockchainContent() {
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResults, setVerifyResults] = useState<Record<string, MockVerifyResult>>({});
  const [demo, setDemo] = useState<DemoToggle | null>(null);
  const [toggleBusy, setToggleBusy] = useState(false);

  const proofs = useApi<MockBlockchainProof[]>("/blockchain/proofs");

  const loadDemo = () => {
    api<DemoToggle>("/blockchain/demo-toggle")
      .then((d) => setDemo(d))
      .catch(() => setDemo(null));
  };

  const setDemoEnabled = async (enabled: boolean) => {
    setToggleBusy(true);
    try {
      await api<DemoToggle>("/blockchain/demo-toggle", {
        method: "POST",
        body: { enabled },
      });
      loadDemo();
      proofs.reload();
    } finally {
      setToggleBusy(false);
    }
  };

  useEffect(() => {
    loadDemo();
  }, []);

  const verify = async (proofId: string) => {
    setVerifying(proofId);
    try {
      const result = await api<MockVerifyResult>(`/blockchain/proofs/${proofId}/verify`);
      setVerifyResults((prev) => ({ ...prev, [proofId]: result }));
    } finally {
      setVerifying(null);
    }
  };

  const columns: Column<MockBlockchainProof>[] = [
    {
      key: "reference",
      header: "Reference / event ID",
      render: (row) => <span className="font-mono text-xs">{row.reference_id}</span>,
    },
    {
      key: "event_type",
      header: "Event type",
      render: (row) => <EventBadge event_type={row.event_type} />,
    },
    {
      key: "record_hash",
      header: "Record hash",
      render: (row) => (
        <span className="font-mono text-xs" title={row.record_hash}>
          {row.record_hash.slice(0, 12)}…{row.record_hash.slice(-4)}
        </span>
      ),
    },
    {
      key: "transaction_hash",
      header: "Tx hash",
      render: (row) => (
        <span className="font-mono text-xs" title={row.transaction_hash}>
          {row.transaction_hash.slice(0, 12)}…{row.transaction_hash.slice(-4)}
        </span>
      ),
    },
    {
      key: "block",
      header: "Block #",
      render: (row) => <span className="num text-xs">{row.block_number}</span>,
    },
    {
      key: "network",
      header: "Network",
      render: (row) => <span className="text-xs text-mute">{row.network}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => <StatusBadge status={row.blockchain_status} />,
    },
    {
      key: "verify",
      header: "Verification",
      align: "right",
      render: (row) => {
        const existing = verifyResults[row.proof_id];
        const result = (
          <>
            {existing ? <ProofVerifyStatus verified={existing.verified} /> : null}
            {existing && (
              <span className="text-[11px] text-mute ml-2">
                mock recomputed {existing.recomputed_record_hash.slice(0, 8)}…
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
  ];

  return (
    <Card
      title="Blockchain Audit Integrity"
      subtitle="MOCK proof layer for demonstration"
      action={
        <Badge tone="neutral">MOCK</Badge>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-mute">
          This page shows the MOCK blockchain proof metadata for critical TradeShield
          events. It is NOT a real blockchain, does NOT contain real transactions, and
          does NOT replace PostgreSQL, which remains the system of record.
        </p>

        <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
          <p className="text-sm font-semibold">Mock proof layer</p>
          <p className="mt-1 text-sm text-mute">
            Record hashes, transaction hashes, and block numbers are deterministic-looking
            demo values. Verification re-computes the stored record hash from the proof
            metadata and compares it to the stored value.
          </p>
        </div>

        <DemoTogglePanel
          demo={demo}
          busy={toggleBusy}
          onLoad={loadDemo}
          onEnable={() => setDemoEnabled(true)}
          onDisable={() => setDemoEnabled(false)}
        />

        {proofs.error ? (
          <ErrorNote message={proofs.error.message} onRetry={proofs.reload} />
        ) : proofs.loading ? (
          <div className="text-sm text-mute">Loading proofs…</div>
        ) : proofs.data && proofs.data.length > 0 ? (
          <DataTable
            columns={columns}
            rows={proofs.data}
            loading={proofs.loading}
            rowKey={(row) => row.proof_id}
            emptyTitle="No proof records yet"
            emptyHint="Run a trade or trigger a blocked order, then refresh."
          />
        ) : (
          <div className="text-sm text-mute">No proof records found.</div>
        )}

        <div className="rounded-xl border border-edge/70 bg-ink-800/40 p-4">
          <p className="text-sm font-semibold">How the demo flag works</p>
          <ul className="mt-2 space-y-1.5 text-sm text-mute">
            <li>• OFF — client@tradeshield.dev trades normally; no flag, no mock proof from this mechanism.</li>
            <li>• ON — the next trade(s) by client@tradeshield.dev are inserted as FLAGGED with a demo note, an ORDER_FLAGGED security event is recorded (null indicator, so it is clearly not a real threat match), and a MOCK blockchain proof is created for the flagged trade.</li>
            <li>• Other users are unaffected. Real threat-screening and security trigger logic is unchanged.</li>
          </ul>
        </div>
      </div>
    </Card>
  );
}

export default function BlockchainPage() {
  return (
    <RequireAdmin>
      <BlockchainContent />
    </RequireAdmin>
  );
}
