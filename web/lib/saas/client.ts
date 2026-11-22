"use client";
// Browser side of accounts and plans. Every call fails soft: when /api/saas is missing or errors,
// the app behaves exactly as before (guest, no banner, nothing blocked).
import { useCallback, useEffect, useState } from "react";
import type { KontoStand } from "./konto";

export type { KontoStand };
const EREIGNIS = "lv-konto";

export async function holeKonto(): Promise<KontoStand | null> {
  try {
    const r = await fetch("/api/saas/me", { cache: "no-store" });
    return r.ok ? ((await r.json()) as KontoStand) : null;
  } catch {
    return null;
  }
}

export function useKonto(): { konto: KontoStand | null; neu: () => void } {
  const [konto, setKonto] = useState<KontoStand | null>(null);
  const neu = useCallback(() => { void holeKonto().then(setKonto); }, []);
  useEffect(() => {
    neu();
    const h = () => neu();
    window.addEventListener(EREIGNIS, h);
    return () => window.removeEventListener(EREIGNIS, h);
  }, [neu]);
  return { konto, neu };
}

export function kontoGeaendert() {
  try { window.dispatchEvent(new Event(EREIGNIS)); } catch { /* not in a browser */ }
}

/** Counts one evaluation for the signed-in user (soft quota). Never throws, never waits for the analysis. */
export function zaehleAuswertung() {
  void fetch("/api/saas/usage", { method: "POST" }).then(() => kontoGeaendert()).catch(() => undefined);
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = (await r.json().catch(() => ({}))) as T & { fehler?: string };
  if (!r.ok) throw Object.assign(new Error(j.fehler || `HTTP ${r.status}`), { status: r.status });
  return j;
}

export async function starteCheckout(plan: "pro" | "company", intervall: "month" | "year", seats?: number, company?: string) {
  const { url } = await post<{ url: string }>("/api/saas/checkout", { plan, intervall, seats, company });
  window.location.href = url;
}

export async function oeffnePortal() {
  const { url } = await post<{ url: string }>("/api/saas/portal");
  window.location.href = url;
}

export async function synchronisiere(): Promise<KontoStand> {
  const s = await post<KontoStand>("/api/saas/sync");
  kontoGeaendert();
  return s;
}
