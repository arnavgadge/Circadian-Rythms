import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { StatusResponse } from "../api/types";

/**
 * Loads the persisted daily result (GET /status?target_date=) for each
 * given date -- a pure read of what the pipeline already stored; it
 * never triggers inference. Results are cached per participant/date
 * for the session, so stepping back and forth through days, or
 * re-opening the page, never repeats a request. At most four requests
 * run at once.
 */
const cache = new Map<string, StatusResponse>();
const failures = new Set<string>();
const CONCURRENCY = 4;

const cacheKey = (participantId: number, date: string) => `${participantId}|${date}`;

export interface DailyStatuses {
  byDate: Record<string, StatusResponse>;
  loaded: number;
  total: number;
  failed: string[];
}

export function useDailyStatuses(participantId: number, dates: string[]): DailyStatuses {
  const [, setVersion] = useState(0);
  const datesKey = dates.join(",");

  useEffect(() => {
    let cancelled = false;
    const missing = datesKey
      .split(",")
      .filter((d) => d && !cache.has(cacheKey(participantId, d)));
    if (missing.length === 0) return;

    let cursor = 0;
    const worker = async () => {
      while (!cancelled && cursor < missing.length) {
        const d = missing[cursor++];
        const k = cacheKey(participantId, d);
        try {
          cache.set(k, await api.getStatus(participantId, d));
          failures.delete(k);
        } catch {
          failures.add(k);
        }
        if (!cancelled) setVersion((v) => v + 1);
      }
    };
    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, missing.length) }, worker));
    return () => {
      cancelled = true;
    };
  }, [participantId, datesKey]);

  const byDate: Record<string, StatusResponse> = {};
  const failed: string[] = [];
  for (const d of dates) {
    const hit = cache.get(cacheKey(participantId, d));
    if (hit) byDate[d] = hit;
    else if (failures.has(cacheKey(participantId, d))) failed.push(d);
  }
  return { byDate, loaded: Object.keys(byDate).length, total: dates.length, failed };
}

/** Test helper: forget cached daily results. */
export function clearDailyStatusCache() {
  cache.clear();
  failures.clear();
}
