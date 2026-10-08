"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getMe } from "./api";
import type { User } from "./types";

/** The logged-in user, or null once we know nobody is logged in. */
export function useMe(): { user: User | null; loading: boolean; refresh: () => void } {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    getMe()
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError) || e.status !== 401) console.error(e);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(refresh, [refresh]);
  return { user, loading, refresh };
}
