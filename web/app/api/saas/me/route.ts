import { NextResponse } from "next/server";
import { aktuellerStand } from "@/lib/saas/konto";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(await aktuellerStand(), { headers: { "Cache-Control": "no-store" } });
}
