// Applies a Stripe subscription to our store (webhook and the post-checkout sync share this).
import { neueFirmaId, nutzerHolen, type Daten } from "./db";
import { aboAusStripe } from "./plaene";

type StripeAbo = Parameters<typeof aboAusStripe>[0];

export function aboAnwenden(d: Daten, sub: StripeAbo, emailHinweis?: string | null) {
  const email = (emailHinweis || sub.metadata?.email || Object.values(d.users).find((u) => u.stripeCustomerId === sub.customer)?.email || "").toLowerCase();
  if (!email) return null;
  const n = nutzerHolen(d, email);
  const a = aboAusStripe(sub);
  n.stripeCustomerId = sub.customer;
  n.subscriptionId = a.subscriptionId;
  n.subscriptionStatus = a.subscriptionStatus;
  n.subscriptionPlan = a.subscriptionPlan;
  n.subscriptionIntervall = a.subscriptionIntervall;
  n.periodEnd = a.periodEnd;
  const aktiv = ["active", "trialing", "past_due"].includes(a.subscriptionStatus);
  if (a.subscriptionPlan === "company") {
    // The buyer's company: seats follow the subscription quantity; the grant ends with the paid period.
    let f = Object.values(d.companies).find((c) => c.quelle === "stripe" && c.members[0] === email);
    if (!f) {
      f = { id: neueFirmaId(), name: sub.metadata?.company || email.split("@")[1] || email, seats: a.seats, expiresAt: null, members: [email], quelle: "stripe", createdAt: new Date().toISOString() };
      d.companies[f.id] = f;
    }
    f.seats = a.seats;
    f.expiresAt = aktiv ? a.periodEnd : new Date().toISOString();
    n.companyId = f.id;
  }
  return n;
}
