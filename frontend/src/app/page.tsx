"use client";

import Link from "next/link";
import { useMe } from "@/lib/hooks";

export default function Home() {
  const { user, loading } = useMe();

  return (
    <>
      <h1>Ask your repository’s issues</h1>
      <div className="card">
        <p>
          Ingest a GitHub repository, then ask questions about its issues. Every answer cites the
          issues it came from, and anything that would change the repository waits for your
          approval.
        </p>
        {loading ? null : user ? (
          <Link className="button primary" href="/repos">
            Go to your repositories
          </Link>
        ) : (
          <a className="button primary" href="/api/auth/login">
            Log in with GitHub
          </a>
        )}
      </div>
    </>
  );
}
