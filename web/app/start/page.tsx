import type { Metadata } from "next";
import { Landing } from "@/components/saas/Landing";

export const metadata: Metadata = { title: "LV Scout – BoQ review before the bid", description: "Find errors, risks and change-order potential in bills of quantities." };

export default function StartPage() {
  return <Landing />;
}
