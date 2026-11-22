import type { Metadata } from "next";
import { Tarife } from "@/components/saas/Tarife";

export const metadata: Metadata = { title: "Plans", description: "Free, Pro and Company plans with evaluation quota." };

export default function TarifePage() {
  return <Tarife />;
}
