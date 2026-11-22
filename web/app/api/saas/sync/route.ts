// After Checkout: reads the customer's subscriptions directly from Stripe, so plans update locally even
// without a webhook (no `stripe listen` needed locally).
import { NextResponse } from "next/server";
import { aboAnwenden } from "@/lib/saas/abo";
import { aendern, lesenNur } from "@/lib/saas/db";
import { sitzungsEmail, stand } from "@/lib/saas/konto";
import { stripe, stripeAktiv } from "@/lib/saas/stripe";

export const dynamic = "force-dynamic";

export async function POST() {
  const s = await sitzungsEmail();
  if (!s) return NextResponse.json({ fehler: "Please sign in first." }, { status: 401 });
  if (!stripeAktiv()) return NextResponse.json(stand(await lesenNur(), s));
  const kunde = (await lesenNur()).users[s.email]?.stripeCustomerId;
  if (!kunde) return NextResponse.json(stand(await lesenNur(), s));
  try {
    const r = await stripe<{ data: Parameters<typeof aboAnwenden>[1][] }>("GET", "subscriptions", { customer: kunde, status: "all", limit: 5 });
    const neuestes = r.data[0];
    const d = await aendern((d) => { if (neuestes) aboAnwenden(d, neuestes, s.email); return d; });
    return NextResponse.json(stand(d, s));
  } catch (e) {
    return NextResponse.json({ fehler: e instanceof Error ? e.message : "Stripe error" }, { status: 502 });
  }
}
