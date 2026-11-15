import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ParticipantResponse } from "../api/types";

/**
 * GET /participants/{id}, fetched at most once per id per session
 * (module-level cache shared by the sidebar and the demo page), so
 * navigating between pages never repeats the request.
 */
const cache = new Map<number, Promise<ParticipantResponse>>();

export function fetchParticipantOnce(id: number): Promise<ParticipantResponse> {
  let pending = cache.get(id);
  if (!pending) {
    pending = api.getParticipant(id);
    cache.set(id, pending);
    pending.catch(() => cache.delete(id)); // allow a retry after a failure
  }
  return pending;
}

export function useParticipant(id: number | null): { participant: ParticipantResponse | null; error: Error | null; loading: boolean } {
  const [state, setState] = useState<{ id: number | null; participant: ParticipantResponse | null; error: Error | null }>({
    id: null,
    participant: null,
    error: null,
  });

  useEffect(() => {
    if (id === null) return;
    let cancelled = false;
    fetchParticipantOnce(id).then(
      (participant) => !cancelled && setState({ id, participant, error: null }),
      (error: unknown) => !cancelled && setState({ id, participant: null, error: error instanceof Error ? error : new Error(String(error)) }),
    );
    return () => {
      cancelled = true;
    };
  }, [id]);

  const current = state.id === id;
  return {
    participant: current ? state.participant : null,
    error: current ? state.error : null,
    loading: id !== null && !current,
  };
}

/** Test helper: forget cached participant lookups. */
export function clearParticipantCache() {
  cache.clear();
}
