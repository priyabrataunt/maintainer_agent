"use client";

import { useEffect, useState } from "react";
import { decideAction, listActions } from "@/lib/api";
import type { PendingAction } from "@/lib/types";

/** Proposed changes to GitHub. Nothing runs until a person approves it here. */
export default function ActionsPanel({
  investigationId,
  refreshKey,
}: {
  investigationId: number | null;
  refreshKey: number;
}) {
  const [actions, setActions] = useState<PendingAction[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (investigationId === null) return;
    listActions(investigationId)
      .then(setActions)
      .catch((e: Error) => setError(e.message));
  }, [investigationId, refreshKey]);

  async function decide(action: PendingAction, approve: boolean) {
    if (investigationId === null) return;
    setBusy(action.id);
    setError(null);
    try {
      const updated = await decideAction(investigationId, action.id, approve);
      setActions((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    } catch (e) {
      // e.g. "You do not own or administer a/b": the action stays pending.
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (actions.length === 0 && !error) return null;

  return (
    <section className="card" aria-labelledby="actions-title">
      <h2 id="actions-title">Proposed changes</h2>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}
      <ul className="plain" data-testid="actions">
        {actions.map((a) => (
          <li key={a.id}>
            <div>
              <code>{a.tool_name}</code>{" "}
              <span className={`badge ${a.status}`}>{a.status}</span>
            </div>
            <div className="muted">{JSON.stringify(a.args)}</div>
            {a.result ? <div className="muted">{a.result}</div> : null}
            {a.status === "pending" ? (
              <div style={{ marginTop: 6 }}>
                <button className="primary" disabled={busy === a.id} onClick={() => decide(a, true)}>
                  Approve
                </button>{" "}
                <button className="danger" disabled={busy === a.id} onClick={() => decide(a, false)}>
                  Reject
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
