// Stripe webhook: keeps plan status in sync. Verifies the signature with STRIPE_WEBHOOK_SECRET.
import { NextResponse } from "next/server";
import { aboAnwenden } from "@/lib/saas/abo";
import { aendern, nutzerHolen } from "@/lib/saas/db";
import { stripe, stripeAktiv } from "@/lib/saas/stripe";
import { signaturPruefen } from "@/lib/saas/stripe-util";

export const dynamic = "force-dynamic";

type Ereignis = { id: string; type: string; data: { object: Record<string, unknown> } };

export async function POST(req: Request) {
  const geheimnis = process.env.STRIPE_WEBHOOK_SECRET;
  if (!geheimnis || !stripeAktiv()) return NextResponse.json({ fehler: "Webhook is not configured." }, { status: 503 });
  const roh = await req.text();
  if (!signaturPruefen(roh, req.headers.get("stripe-signature"), geheimnis)) {
    return NextResponse.json({ fehler: "Invalid signature." }, { status: 400 });
  }
  const ev = JSON.parse(roh) as Ereignis;
  const o = ev.data.object;
  try {
    if (ev.type === "checkout.session.completed" && typeof o.subscription === "string") {
      const sub = await stripe<Parameters<typeof aboAnwenden>[1]>("GET", `subscriptions/${o.subscription}`);
      const email = (o.client_reference_id as string) || ((o.metadata as Record<string, string>)?.email ?? null);
      await aendern((d) => {
        if (email) nutzerHolen(d, email).stripeCustomerId = o.customer as string;
        aboAnwenden(d, sub, email);
      });
    } else if (ev.type.startsWith("customer.subscription.")) {
      await aendern((d) => { aboAnwenden(d, o as Parameters<typeof aboAnwenden>[1]); });
    }
  } catch (e) {
    return NextResponse.json({ fehler: e instanceof Error ? e.message : "Webhook error" }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
