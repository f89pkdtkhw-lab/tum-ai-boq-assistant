// Counts one evaluation for the signed-in user. Soft quota: never refuses, the UI shows a banner instead.
import { NextResponse } from "next/server";
import { aendern, nutzerHolen } from "@/lib/saas/db";
import { sitzungsEmail, stand } from "@/lib/saas/konto";
import { monatsSchluessel } from "@/lib/saas/plaene";

export const dynamic = "force-dynamic";

export async function POST() {
  const s = await sitzungsEmail();
  if (!s) return NextResponse.json({ gezaehlt: false });
  const d = await aendern((d) => {
    const n = nutzerHolen(d, s.email, s.name);
    const m = monatsSchluessel();
    n.usage[m] = (n.usage[m] ?? 0) + 1;
    return d;
  });
  return NextResponse.json({ gezaehlt: true, ...stand(d, s) });
}
