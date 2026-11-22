import type { Metadata } from "next";
import { Suspense } from "react";
import { KontoSeite } from "@/components/saas/KontoSeite";

export const metadata: Metadata = { title: "Account", description: "Sign in, plan and evaluation quota." };

export default function KontoPage() {
  return <Suspense><KontoSeite /></Suspense>;
}
