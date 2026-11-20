// Die Schnittstelle zwischen Oberfläche und Backend. Spiegelt die Routen in api/app/main.py.
// Änderungen hier nur zusammen mit dem Backend und mit @all-Post auf dem Board.

export type Health = { ok: boolean; provider: string; model: string; mock: boolean };
export type Answer = { answer: string; provider: string; model: string; ms: number };
export type Example = { id: string; titel: string; beschreibung: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Anfrage fehlgeschlagen (${response.status}).`);
  return body as T;
}

export const api = {
  health: () => call<Health>("/health"),
  examples: () => call<{ items: Example[] }>("/api/beispiele").then((body) => body.items ?? []),
  ask: (question: string) =>
    call<Answer>("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }),
};
