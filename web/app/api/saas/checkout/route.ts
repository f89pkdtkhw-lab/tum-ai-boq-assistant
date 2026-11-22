// Starts Stripe Checkout (subscription) for Pro or Company. Needs a signed-in user and STRIPE_SECRET_KEY.
import { NextResponse } from "next/server";
import { aendern, nutzerHolen } from "@/lib/saas/db";
import { sitzungsEmail } from "@/lib/saas/konto";
import { lookupKey, type Intervall } from "@/lib/saas/plaene";
import { preisId, stripe, stripeAktiv } from "@/lib/saas/stripe";
import { basisUrl } from "@/lib/saas/url";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  if (!stripeAktiv()) return NextResponse.json({ fehler: "Stripe is not configured." }, { status: 503 });
  const s = await sitzungsEmail();
  if (!s) return NextResponse.json({ fehler: "Please sign in first." }, { status: 401 });
  const body = (await req.json().catch(() => ({}))) as { plan?: string; intervall?: string; seats?: number; company?: string };
  const plan = body.plan === "company" ? "company" : "pro";
  const intervall: Intervall = body.intervall === "year" ? "year" : "month";
  const seats = plan === "company" ? Math.min(500, Math.max(1, Math.round(Number(body.seats) || 3))) : 1;
  try {
    const price = await preisId(lookupKey(plan, intervall));
    const kunde = await aendern(async (d) => {
      const n = nutzerHolen(d, s.email, s.name);
      if (!n.stripeCustomerId) {
        const c = await stripe<{ id: string }>("POST", "customers", { email: s.email, name: s.name ?? undefined, metadata: { app: "lv-scout" } });
        n.stripeCustomerId = c.id;
      }
      return n.stripeCustomerId;
    });
    const basis = basisUrl(req);
    const meta = { app: "lv-scout", email: s.email, plan, seats: String(seats), company: (body.company ?? "").slice(0, 80) };
    const session = await stripe<{ url: string }>("POST", "checkout/sessions", {
      mode: "subscription",
      customer: kunde,
      client_reference_id: s.email,
      line_items: [{ price, quantity: seats }],
      allow_promotion_codes: true,
      metadata: meta,
      subscription_data: { metadata: meta },
      success_url: `${basis}/konto?checkout=ok`,
      cancel_url: `${basis}/tarife?checkout=abbruch`,
    });
    return NextResponse.json({ url: session.url });
  } catch (e) {
    return NextResponse.json({ fehler: e instanceof Error ? e.message : "Stripe error" }, { status: 502 });
  }
}
