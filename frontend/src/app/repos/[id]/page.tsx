"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ActionsPanel from "@/components/ActionsPanel";
import SourcesPanel from "@/components/SourcesPanel";
import { askFollowUp, followJob, getRepository, startInvestigation } from "@/lib/api";
import { describeStatus, outcomeNote } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { InvestigationResult, Repository, Source } from "@/lib/types";

type Turn = {
  id: number;
  role: "user" | "assistant";
  text: string;
  note?: string | null;
  isError?: boolean;
};

export default function Chat() {
  const params = useParams<{ id: string }>();
  const repoId = Number(params.id);
  const { user, loading: loadingUser } = useMe();

  const [repo, setRepo] = useState<Repository | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [investigationId, setInvestigationId] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionsKey, setActionsKey] = useState(0);
  const nextId = useRef(1);
  // Same question retried => same key => the server returns the same job instead of a new one.
  const pending = useRef<{ question: string; key: string } | null>(null);
  const cancelStream = useRef<() => void>(() => {});

  useEffect(() => {
    if (!Number.isFinite(repoId)) return;
    getRepository(repoId)
      .then(setRepo)
      .catch(() => setRepo(null));
    return () => cancelStream.current();
  }, [repoId]);

  const addTurn = (turn: Omit<Turn, "id">) =>
    setTurns((prev) => [...prev, { ...turn, id: nextId.current++ }]);

  const addSources = (found: Source[]) =>
    setSources((prev) => {
      const known = new Set(prev.map((s) => s.issue_number));
      return [...found.filter((s) => !known.has(s.issue_number)), ...prev];
    });

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || busy) return;

    setBusy(true);
    setQuestion("");
    addTurn({ role: "user", text });
    try {
      if (investigationId === null) {
        if (pending.current?.question !== text) {
          pending.current = { question: text, key: crypto.randomUUID() };
        }
        setProgress("Queued…");
        const accepted = await startInvestigation(repoId, text, pending.current.key);
        const stream = followJob(accepted.job_id, (s, a) => setProgress(describeStatus(s, a)));
        cancelStream.current = stream.cancel;
        const job = await stream.done;
        pending.current = null;
        if (job.status === "failed") {
          addTurn({ role: "assistant", text: job.error ?? "The job failed.", isError: true });
          return;
        }
        const result = job.result as unknown as InvestigationResult;
        setInvestigationId(result.investigation_id);
        addSources(result.sources ?? []);
        addTurn({ role: "assistant", text: result.answer, note: outcomeNote(result.status) });
      } else {
        setProgress("Thinking…");
        const reply = await askFollowUp(investigationId, text);
        addSources(reply.citations);
        addTurn({ role: "assistant", text: reply.answer, note: outcomeNote(reply.status) });
      }
      setActionsKey((k) => k + 1);
    } catch (err) {
      addTurn({ role: "assistant", text: (err as Error).message, isError: true });
    } finally {
      setProgress("");
      setBusy(false);
    }
  }

  if (!loadingUser && !user) {
    return (
      <div className="card">
        <p>Log in to ask questions.</p>
        <a className="button primary" href="/api/auth/login">
          Log in with GitHub
        </a>
      </div>
    );
  }

  return (
    <>
      <p>
        <Link href="/repos">← Repositories</Link>
      </p>
      <h1>{repo ? `${repo.owner}/${repo.name}` : "Repository"}</h1>
      <div className="layout">
        <section className="card" aria-label="Conversation">
          <div data-testid="transcript">
            {turns.length === 0 ? (
              <p className="muted">
                Ask about this repository’s issues, e.g. “why does the app crash on startup?”
              </p>
            ) : null}
            {turns.map((t) => (
              <div
                key={t.id}
                className={`turn ${t.role}${t.isError ? " error" : ""}`}
                data-testid={`turn-${t.role}`}
                role={t.isError ? "alert" : undefined}
              >
                {t.text}
                {t.note ? <div className="note">{t.note}</div> : null}
              </div>
            ))}
          </div>
          <div className="progress" aria-live="polite" data-testid="progress">
            {progress}
          </div>
          <form onSubmit={ask}>
            <label htmlFor="question" className="muted">
              {investigationId === null ? "Your question" : "Ask a follow-up"}
            </label>
            <textarea
              id="question"
              rows={3}
              value={question}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(e);
              }}
              disabled={busy}
            />
            <div style={{ marginTop: 8 }}>
              <button className="primary" type="submit" disabled={busy || !question.trim()}>
                {busy ? "Working…" : "Ask"}
              </button>
            </div>
          </form>
        </section>

        <div>
          <SourcesPanel repo={repo} sources={sources} />
          <ActionsPanel investigationId={investigationId} refreshKey={actionsKey} />
        </div>
      </div>
    </>
  );
}
