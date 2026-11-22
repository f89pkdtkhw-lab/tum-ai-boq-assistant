"use client";
import { useEffect, useState } from "react";
import { beobachteSitzung, evaluationListe, ladeSitzung, type EvaluationEintrag, type EvaluationSitzung } from "./evaluation-session";

/** Live view of the current and recent evaluations for the sidebar and top bar. */
export function useEvaluationSitzung(): EvaluationSitzung & { liste: EvaluationEintrag[] } {
  const [sitzung, setSitzung] = useState<EvaluationSitzung>({ aktuell: null, historie: [] });
  useEffect(() => {
    const sync = () => setSitzung(ladeSitzung());
    sync();
    return beobachteSitzung(sync);
  }, []);
  return { ...sitzung, liste: evaluationListe(sitzung) };
}
