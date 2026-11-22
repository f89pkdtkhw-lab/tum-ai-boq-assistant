// Stripe Customer Portal: manage or cancel the subscription, update the card, download invoices.
import { NextResponse } from "next/server";
import { lesenNur } from "@/lib/saas/db";
import { sitzungsEmail } from "@/lib/saas/konto";
import { stripe, stripeAktiv } from "@/lib/saas/stripe";
import { basisUrl } from "@/lib/saas/url";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  if (!stripeAktiv()) return NextResponse.json({ fehler: "Stripe is not configured." }, { status: 503 });
  const s = await sitzungsEmail();
  if (!s) return NextResponse.json({ fehler: "Please sign in first." }, { status: 401 });
  const kunde = (await lesenNur()).users[s.email]?.stripeCustomerId;
  if (!kunde) return NextResponse.json({ fehler: "No subscription yet." }, { status: 404 });
  try {
    const p = await stripe<{ url: string }>("POST", "billing_portal/sessions", { customer: kunde, return_url: `${basisUrl(req)}/konto` });
    return NextResponse.json({ url: p.url });
  } catch (e) {
    return NextResponse.json({ fehler: e instanceof Error ? e.message : "Stripe error" }, { status: 502 });
  }
}
