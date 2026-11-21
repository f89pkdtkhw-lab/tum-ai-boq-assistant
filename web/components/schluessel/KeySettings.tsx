"use client";

// #156: enter the Claude API key in the header. The key goes to the backend once by POST and is
// cleared from this component right after saving; the backend only ever answers "key set: yes/no".
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, type KeyState } from "@/lib/api";
import styles from "./key-settings.module.css";

type Message = { kind: "ok" | "error" | "info"; text: string } | null;

/** `compact`: small key button for the navy top bar of the redesign; the panel opens as a popover below it. */
export function KeySettings({ compact = false }: { compact?: boolean } = {}) {
  const [state, setState] = useState<KeyState | null | "offline">(null);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [persist, setPersist] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | "clear" | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const refresh = useCallback(() => {
    api.keyState().then(setState).catch(() => setState("offline"));
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !wrapper.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  async function run(kind: "save" | "test" | "clear", action: () => Promise<void>) {
    setBusy(kind);
    setMessage(null);
    try {
      await action();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Request failed." });
    } finally {
      setBusy(null);
    }
  }

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    run("save", async () => {
      const next = await api.setKey({ key: key.trim(), model: model.trim() || undefined, persist });
      setKey("");
      setState(next);
      setMessage({ kind: "ok", text: next.persisted ? "Key saved in memory and in .env.local." : "Key saved in memory until the backend restarts." });
      window.dispatchEvent(new Event("llm-config-changed"));
    });
  };
  const test = () => run("test", async () => {
    const probe = await api.testKey();
    setMessage(probe.ok
      ? { kind: "ok", text: `OK · ${probe.provider} · ${probe.model} answered in ${probe.ms ?? 0} ms.` }
      : { kind: "error", text: probe.error || "The test call failed." });
  });
  const clear = () => run("clear", async () => {
    const next = await api.clearKey();
    setState(next);
    setMessage({ kind: "info", text: next.key_set ? "UI key removed; a key from the environment or .env.local is still used." : "Key removed. The app runs on the offline mock." });
    window.dispatchEvent(new Event("llm-config-changed"));
  });

  const live = state && state !== "offline" && !state.mock;
  const chip = state === null ? { cls: "", text: "Model …" }
    : state === "offline" ? { cls: styles.off, text: "Backend offline" }
    : state.mock ? { cls: styles.mock, text: "Mock · no API key" }
    : { cls: styles.live, text: `${state.provider} · ${state.model}` };

  return (
    <div className={styles.wrapper} ref={wrapper}>
      {compact ? (
        <button type="button" className={`${styles.keyButton} ${chip.cls}`} aria-expanded={open} aria-controls={panelId}
          onClick={() => { setOpen(!open); if (!open) refresh(); }} title={`Claude API key · ${chip.text}`} aria-label={`Claude API key (${chip.text})`}>
          <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M14.5 4a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11zM10.6 13.4L4 20M7 17l2 2M5 19l1.5 1.5M16 8.5h.01" />
          </svg>
          <span className={styles.keyDot} aria-hidden="true" />
        </button>
      ) : (
        <button type="button" className={`${styles.chip} ${chip.cls}`} aria-expanded={open} aria-controls={panelId}
          onClick={() => { setOpen(!open); if (!open) refresh(); }} title="Model and Claude API key">
          <span className={styles.dot} aria-hidden="true" />
          {chip.text}
        </button>
      )}
      {open && (
        <div className={`${styles.panel} ${compact ? styles.compactPanel : ""}`} id={panelId} role="dialog" aria-label="Claude API key">
          {state === "offline" || state === null ? (
            <p className={styles.note}>The backend is not reachable. Start it with <code>python tools/dev.py</code>.</p>
          ) : (
            <>
              <p className={styles.status}>
                Key set: <b>{state.key_set ? "yes" : "no"}</b>
                {state.key_source === "ui" && " (entered here)"}
                {state.key_source === "env" && " (environment / .env.local)"}
                {" · "}Model: <b>{state.model}</b>
              </p>
              {state.mock && (
                <p className={styles.notice} role="status">
                  Mock mode: without a Claude API key, model findings are offline demonstration answers, not real review results.
                  {state.reason && <><br /><small>{state.reason}</small></>}
                </p>
              )}
              {state.ui_enabled ? (
                <form onSubmit={save} className={styles.form}>
                  <label className={styles.label}>
                    Claude API key
                    <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={live ? "Enter a new key to replace it" : "sk-ant-…"}
                      autoComplete="off" spellCheck={false} required minLength={20} className={styles.input} />
                  </label>
                  <label className={styles.label}>
                    <span>Model <span className={styles.optional}>(optional)</span></span>
                    <input type="text" value={model} onChange={(e) => setModel(e.target.value)} placeholder="claude-sonnet-5-5"
                      autoComplete="off" spellCheck={false} className={styles.input} />
                  </label>
                  <label className={styles.check}>
                    <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
                    <span>Also save in <code>.env.local</code> on the server (kept after a restart, never committed)</span>
                  </label>
                  <div className={styles.actions}>
                    <button type="submit" className={styles.primary} disabled={busy !== null || key.trim().length < 20}>
                      {busy === "save" ? "Saving …" : "Save"}
                    </button>
                    <button type="button" className={styles.secondary} onClick={test} disabled={busy !== null}>
                      {busy === "test" ? "Testing …" : "Test"}
                    </button>
                    {state.key_source === "ui" && (
                      <button type="button" className={styles.secondary} onClick={clear} disabled={busy !== null}>
                        {busy === "clear" ? "Removing …" : "Remove"}
                      </button>
                    )}
                  </div>
                </form>
              ) : (
                <p className={styles.note}>Changing the key is disabled on this server (LLM_KEY_UI=off).</p>
              )}
              {message && (
                <p className={`${styles.message} ${styles[message.kind]}`} role={message.kind === "error" ? "alert" : "status"}>
                  {message.text}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
