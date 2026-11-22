import type { Metadata } from "next";
import { Suspense } from "react";
import { Vault } from "@/components/vault/Vault";

export const metadata: Metadata = {
  title: "Vault",
  description: "All bills, regulations, price lists, the price database, reports, research and history in one place, stored locally.",
};

export default function VaultPage() {
  return <Suspense><Vault /></Suspense>;
}
