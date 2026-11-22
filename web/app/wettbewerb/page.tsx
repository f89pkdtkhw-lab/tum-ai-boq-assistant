import type { Metadata } from "next";
import { Wettbewerb } from "@/components/wettbewerb/Wettbewerb";

export const metadata: Metadata = { title: "Competitors", description: "Tender opening results, each bidder's usual margin and unrealistic bidders." };

export default function WettbewerbPage() {
  return <Wettbewerb />;
}
