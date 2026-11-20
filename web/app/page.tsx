"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, type Answer, type Example, type Health } from "@/lib/api";

// Platzhalter-Startseite: zeigt den ganzen Weg Oberfläche → Backend → Modell.
// Nach dem Kickoff baut die Oberflächen-Crew hier das Produkt des Cases.
export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [question, setQuestion] = useState("Was kann dieser Prototyp?");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setError("Backend nicht erreichbar. Läuft python tools/dev.py?"));
    api.examples().then(setExamples).catch(() => {});
  }, []);

  async function ask(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setAnswer(await api.ask(question));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Anfrage fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="top">
        <span className="brand">◆ Produktname</span>
        <span className={`status ${health ? (health.mock ? "mock" : "live") : "off"}`}>
          {health ? `${health.provider} · ${health.model}` : "Backend offline"}
        </span>
      </header>

      <section className="hero">
        <p className="kicker">TUM.ai Construction Hackathon 2026</p>
        <h1>Ein Satz, der das Problem des Partners auf den Punkt bringt.</h1>
        <p className="lead">Platzhalter bis zum Kickoff. Danach steht hier, wer das Problem hat und was unser Prototyp für ihn löst.</p>
      </section>

      <form className="card ask" onSubmit={ask}>
        <label htmlFor="q">Frage an den Prototyp</label>
        <div className="row">
          <input id="q" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={4000} />
          <button disabled={busy || !question.trim()}>{busy ? "Denkt …" : "Fragen"}</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {answer && (
          <div className="answer" aria-live="polite">
            <p>{answer.answer}</p>
            <small>{answer.provider} · {answer.model} · {answer.ms} ms</small>
          </div>
        )}
      </form>

      <section className="grid">
        {examples.map((example) => (
          <article className="card" key={example.id}>
            <h2>{example.titel}</h2>
            <p>{example.beschreibung}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
