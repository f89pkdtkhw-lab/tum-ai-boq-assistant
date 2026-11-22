import type { Metadata } from "next";
import { Suspense } from "react";
import { EmailBestaetigen } from "@/components/saas/KontoLink";

export const metadata: Metadata = { title: "Confirm email" };

export default function BestaetigenPage() {
  return <Suspense><EmailBestaetigen /></Suspense>;
}
