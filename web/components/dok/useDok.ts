"use client";

import { useEffect, useReducer } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { abonniere, inSprache } from "@/lib/dokument-sprache";

/** d(text): a document text (item text, title) in the chosen UI language – glossary at once, model translation when it arrives. */
export function useDok() {
  const { e } = useEinstellungen();
  const [, neu] = useReducer((x: number) => x + 1, 0);
  useEffect(() => abonniere(neu), []);
  return (text: string | null | undefined) => inSprache(text, e.sprache);
}
