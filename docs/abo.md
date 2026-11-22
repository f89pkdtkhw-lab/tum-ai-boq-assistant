# Accounts, plans and Stripe (LV Scout)

Login, plans with an evaluation quota, Stripe Checkout and an admin page. **Everything is optional**: without
any of the variables below the app works exactly as before, the top bar shows "Sign in · Demo", and no
evaluation is ever blocked.

## Pages and routes

| Path | What |
| --- | --- |
| `/start` | Landing page (hero with logo, features) |
| `/tarife` | Pricing: Free · Pro · Company with evaluations per month, monthly/yearly switch |
| `/konto` | Sign in (Google, demo login with email only), plan, usage bar, Stripe portal, sign out |
| `/admin` | Unlock company plans by hand (name, seats, expiry, members), list accounts. Allowed for `ADMIN_EMAILS` or with the developer code (`DEV_OPTIONS_CODE`, default 2211) |
| `/api/auth/*` | Auth.js (NextAuth v5), JWT sessions |
| `/api/saas/me` | Current account, plan, quota, which features are configured |
| `/api/saas/usage` | +1 evaluation (called when an evaluation starts; soft quota, never refuses) |
| `/api/saas/checkout` · `/portal` · `/sync` | Stripe Checkout, Customer Portal, read subscription after checkout |
| `/api/saas/webhook` | Stripe webhook (`checkout.session.completed`, `customer.subscription.*`), signature checked |
| `/api/saas/admin` | Admin list and company grants |

Code: `web/lib/saas/` (plans and quota rules in `plaene.ts`, tested in `web/lib/saas.test.mjs`),
UI in `web/components/saas/`. Data: `web/.data/saas.json` (git-ignored; folder via `LV_SCOUT_DATA_DIR`).

## Plans

| Plan | Quota | Price (test mode) | Stripe lookup key |
| --- | --- | --- | --- |
| Free | 3 evaluations / month | 0 € | – |
| Pro | 50 evaluations / month | 29 € / month · 290 € / year | `lv_scout_pro_monthly`, `lv_scout_pro_yearly` |
| Company | 200 evaluations / seat / month | 49 € / seat / month · 490 € / seat / year | `lv_scout_company_seat_monthly`, `lv_scout_company_seat_yearly` |

Effective plan: active company grant (admin or Stripe Company) → active Pro subscription → Free. Not signed in = Demo (unlimited).
The quota is soft: a banner with an upgrade button appears above the upload when 1 or 0 evaluations are left.

Products and prices exist in **Stripe test mode on the existing account "Print Pool"** (metadata `app=lv-scout`).
The app looks prices up by lookup key, so no price IDs need to be configured.

## Activate

Put the values in `.env.local` in the repository root (or `web/.env.local`), never in commits, issues or chat:

1. **Google login:** create an OAuth client (type Web) in Google Cloud, redirect URI
   `http://localhost:3000/api/auth/callback/google`, then set `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET` and `AUTH_SECRET`.
2. **Stripe:** `STRIPE_SECRET_KEY=sk_test_…` from Print Pool (Dashboard → Developers → API keys, test mode).
   Checkout then works; after paying, `/konto?checkout=ok` reads the subscription directly from Stripe, so a
   webhook is not required locally. For live updates (cancellations, renewals):
   `stripe listen --forward-to localhost:3000/api/saas/webhook` and set the printed `STRIPE_WEBHOOK_SECRET`.
   The Customer Portal configuration already exists in test mode (`bpc_1UePYIE6CuZdLn5LVFNjC77b`, default): cancel at period end, switch Pro/Company and seats, invoices, card.
3. **Admin:** `ADMIN_EMAILS=you@example.com` or open `/admin` with the developer code.

Restart `python3 tools/dev.py` after changing the variables. Test card: `4242 4242 4242 4242`, any future date, any CVC.
