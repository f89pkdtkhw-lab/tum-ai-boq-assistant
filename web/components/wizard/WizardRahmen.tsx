"use client";

import type { ReactNode } from "react";
import { WizardFuss, WizardLeiste, WizardProvider } from "./Wizard";
import { SitzungsJobTracker } from "./SitzungsJobTracker";

/** Client wrapper so the layout can put the progress bar around every page under a Suspense boundary. */
export function WizardRahmen({ children }: { children: ReactNode }) {
  return (
    <WizardProvider>
      <SitzungsJobTracker />
      <WizardLeiste />
      <div className="app-page">{children}</div>
      <WizardFuss />
    </WizardProvider>
  );
}
