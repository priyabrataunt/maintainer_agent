"use client";

import Link from "next/link";
import { logout } from "@/lib/api";
import { useMe } from "@/lib/hooks";

export default function UserBar() {
  const { user, loading, refresh } = useMe();

  return (
    <header className="bar">
      <Link className="brand" href="/">
        Maintainer Agent
      </Link>
      <nav className="user" aria-label="Account">
        {loading ? null : user ? (
          <>
            {user.avatar_url ? <img src={user.avatar_url} alt="" /> : null}
            <span data-testid="login">{user.login}</span>
            <button
              onClick={async () => {
                await logout().catch(() => undefined);
                refresh();
              }}
            >
              Log out
            </button>
          </>
        ) : (
          <a className="button primary" href="/api/auth/login">
            Log in with GitHub
          </a>
        )}
      </nav>
    </header>
  );
}
