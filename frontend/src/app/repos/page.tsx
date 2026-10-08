"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createRepository,
  followJob,
  listRepositories,
  syncRepository,
} from "@/lib/api";
import { describeStatus } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Repository } from "@/lib/types";

export default function Repos() {
  const { user, loading: loadingUser } = useMe();
  const [repos, setRepos] = useState<Repository[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [syncStatus, setSyncStatus] = useState<Record<number, string>>({});
  const syncKeys = useRef<Record<number, string>>({});

  const load = useCallback(() => {
    listRepositories()
      .then(setRepos)
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createRepository(owner.trim(), name.trim());
      setOwner("");
      setName("");
      load();
    } catch (err) {
      setError((err as ApiError).message);
    }
  }

  async function sync(repo: Repository) {
    setError(null);
    // One key per button press: pressing again while it runs returns the same job.
    const key = (syncKeys.current[repo.id] ??= crypto.randomUUID());
    try {
      const accepted = await syncRepository(repo.id, key);
      const { done } = followJob(accepted.job_id, (s, a) =>
        setSyncStatus((prev) => ({ ...prev, [repo.id]: describeStatus(s, a) })),
      );
      const job = await done;
      delete syncKeys.current[repo.id];
      if (job.status === "failed") {
        setSyncStatus((prev) => ({ ...prev, [repo.id]: `Sync failed: ${job.error ?? "unknown error"}` }));
      } else {
        const r = job.result as { issues?: number; chunks_created?: number } | null;
        setSyncStatus((prev) => ({
          ...prev,
          [repo.id]: `Synced ${r?.issues ?? 0} issues (${r?.chunks_created ?? 0} new chunks).`,
        }));
      }
    } catch (err) {
      delete syncKeys.current[repo.id];
      setSyncStatus((prev) => ({ ...prev, [repo.id]: (err as Error).message }));
    }
  }

  if (!loadingUser && !user) {
    return (
      <div className="card">
        <p>Log in to see your repositories.</p>
        <a className="button primary" href="/api/auth/login">
          Log in with GitHub
        </a>
      </div>
    );
  }

  return (
    <>
      <h1>Repositories</h1>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}

      <div className="card">
        <h2>Add a repository</h2>
        <form className="inline" onSubmit={add}>
          <input aria-label="Owner" placeholder="owner (e.g. octocat)" value={owner}
            onChange={(e) => setOwner(e.target.value)} required />
          <input aria-label="Name" placeholder="repo (e.g. hello-world)" value={name}
            onChange={(e) => setName(e.target.value)} required />
          <button className="primary" type="submit">Add</button>
        </form>
      </div>

      <div className="card">
        {repos === null ? (
          <p className="muted">Loading…</p>
        ) : repos.length === 0 ? (
          <p className="muted">No repositories yet. Add one above, then sync it.</p>
        ) : (
          <ul className="plain">
            {repos.map((repo) => (
              <li key={repo.id} data-testid={`repo-${repo.id}`}>
                <div className="row">
                  <div>
                    <strong>{repo.owner}/{repo.name}</strong>
                    {repo.description ? <div className="muted">{repo.description}</div> : null}
                  </div>
                  <div>
                    <button onClick={() => sync(repo)}>Sync</button>{" "}
                    <Link className="button primary" href={`/repos/${repo.id}`}>
                      Ask questions
                    </Link>
                  </div>
                </div>
                {syncStatus[repo.id] ? (
                  <div className="muted" aria-live="polite">{syncStatus[repo.id]}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
