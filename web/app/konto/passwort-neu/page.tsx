import type { Metadata } from "next";
import { Suspense } from "react";
import { PasswortNeu } from "@/components/saas/KontoLink";

export const metadata: Metadata = { title: "New password" };

export default function PasswortNeuPage() {
  return <Suspense><PasswortNeu /></Suspense>;
}
