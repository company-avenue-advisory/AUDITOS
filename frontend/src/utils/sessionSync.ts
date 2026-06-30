"use client";

import { useEffect, useRef, useCallback } from "react";
import { apiRequest } from "./api";

export interface SessionState {
  active_batch_id?: string | null;
  active_task_id?: string | null;
  active_page?: string;
  selected_invoice_type?: string;
  selected_model?: string;
  scroll_position?: number;
  context_blob?: string | null;
}

export interface ResumableSession extends SessionState {
  updated_at?: string;
  batch_status?: string;
  batch_total_files?: number;
}

/**
 * Debounced auto-save hook. Call this with the current page state; it will
 * persist it to /api/me/session every 3 seconds when state changes.
 *
 * Usage:
 *   useSessionSync({ active_batch_id: batchId, active_page: "invoice-extractor", ... });
 */
export function useSessionSync(state: SessionState, enabled = true) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<string>("");

  const save = useCallback(async (s: SessionState) => {
    try {
      await apiRequest("/api/me/session", {
        method: "POST",
        body: JSON.stringify(s),
      });
    } catch {
      // silent — session save is best-effort
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const serialized = JSON.stringify(state);
    if (serialized === lastSaved.current) return;

    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      lastSaved.current = serialized;
      save(state);
    }, 3000);

    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [state, enabled, save]);
}

/** Fetch the user's last saved session from the backend. */
export async function fetchActiveSession(): Promise<ResumableSession | null> {
  try {
    const res = await apiRequest("/api/me/session");
    if (!res.ok) return null;
    const data = await res.json();
    return data.session ?? null;
  } catch {
    return null;
  }
}

/** Clear the active session (e.g. user starts a fresh audit). */
export async function clearActiveSession(): Promise<void> {
  try {
    await apiRequest("/api/me/session", { method: "DELETE" });
  } catch {
    // silent
  }
}

/** Fetch user preferences. */
export async function fetchPreferences() {
  try {
    const res = await apiRequest("/api/me/preferences");
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** Save user preferences. */
export async function savePreferences(prefs: {
  theme?: string;
  default_invoice_type?: string;
  default_model?: string;
  default_export_schema?: string;
}) {
  try {
    await apiRequest("/api/me/preferences", {
      method: "PUT",
      body: JSON.stringify(prefs),
    });
  } catch {
    // silent
  }
}
