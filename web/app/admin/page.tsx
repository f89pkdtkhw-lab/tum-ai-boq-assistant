import type { Metadata } from "next";
import { AdminSeite } from "@/components/saas/AdminSeite";

export const metadata: Metadata = { title: "Admin", robots: { index: false } };

export default function AdminPage() {
  return <AdminSeite />;
}
