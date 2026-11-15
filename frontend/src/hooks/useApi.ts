import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
}

/**
 * Fetches once (and whenever `deps` change), tracking loading/error
 * state. Server state only -- no caching layer, no duplicated copies
 * of the same response (see docs/ui_architecture.md "State management").
 *
 * `enabled = false` skips the request entirely (used for requests that
 * depend on another response, e.g. the day's observations once the
 * status response says which day is being shown), so nothing is ever
 * fetched speculatively.
 */
export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  enabled = true,
): AsyncState<T> & { refetch: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: enabled, error: null });
  const requestId = useRef(0);

  const load = useCallback(() => {
    const id = ++requestId.current;
    if (!enabled) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    setState((prev) => ({ ...prev, loading: true, error: null }));
    fetcher()
      .then((data) => {
        if (id === requestId.current) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (id === requestId.current) {
          setState({ data: null, loading: false, error: error instanceof Error ? error : new Error(String(error)) });
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  return { ...state, refetch: load };
}

/** For a one-shot action (mutation) the caller triggers explicitly,
 * e.g. running inference or submitting an outcome. */
export function useAction<TArgs extends unknown[], TResult>(action: (...args: TArgs) => Promise<TResult>) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  // Always call the *latest* action closure (it captures current form
  // values); updated after every commit, before any user event fires.
  const actionRef = useRef(action);
  useLayoutEffect(() => {
    actionRef.current = action;
  });

  const run = useCallback(async (...args: TArgs) => {
    setLoading(true);
    setError(null);
    try {
      const result = await actionRef.current(...args);
      setLoading(false);
      return result;
    } catch (err) {
      const normalized = err instanceof Error ? err : new Error(String(err));
      setError(normalized);
      setLoading(false);
      throw normalized;
    }
  }, []);

  const reset = useCallback(() => setError(null), []);

  return { run, loading, error, reset };
}
