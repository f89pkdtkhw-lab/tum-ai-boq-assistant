// Tiny JSON store for accounts, subscriptions, company grants and quota counters.
// File: $LV_SCOUT_DATA_DIR/saas.json (default web/.data/, git-ignored). One Next server process, so a write queue is enough.
import { promises as fs } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { Firma, Nutzer } from "./plaene";

export type Daten = { users: Record<string, Nutzer>; companies: Record<string, Firma>; events: string[] };

export function datenOrdner(): string {
  return process.env.LV_SCOUT_DATA_DIR || path.join(process.cwd(), ".data");
}
const datei = () => path.join(datenOrdner(), "saas.json");

async function lesen(): Promise<Daten> {
  try {
    const roh = JSON.parse(await fs.readFile(datei(), "utf8")) as Partial<Daten>;
    return { users: roh.users ?? {}, companies: roh.companies ?? {}, events: roh.events ?? [] };
  } catch {
    return { users: {}, companies: {}, events: [] };
  }
}

async function schreiben(d: Daten) {
  await fs.mkdir(datenOrdner(), { recursive: true });
  const tmp = `${datei()}.${process.pid}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(d, null, 2));
  await fs.rename(tmp, datei());
}

let kette: Promise<unknown> = Promise.resolve();

/** Serialised read-modify-write. The callback may mutate `d`; its return value is passed through. */
export function aendern<T>(fn: (d: Daten) => T | Promise<T>): Promise<T> {
  const lauf = kette.then(async () => {
    const d = await lesen();
    const r = await fn(d);
    await schreiben(d);
    return r;
  });
  kette = lauf.catch(() => undefined);
  return lauf;
}

export async function lesenNur(): Promise<Daten> {
  await kette.catch(() => undefined);
  return lesen();
}

export function nutzerHolen(d: Daten, email: string, name?: string | null): Nutzer {
  const key = email.trim().toLowerCase();
  const n = d.users[key] ?? { email: key, createdAt: new Date().toISOString(), usage: {} };
  if (name && !n.name) n.name = name;
  d.users[key] = n;
  return n;
}

export function neueFirmaId(): string {
  return `co_${randomUUID().slice(0, 8)}`;
}
