# Accounts, plans and Stripe (LV Scout)

Login, plans with an evaluation quota, Stripe Checkout and an admin page. Sign-in works with **Google** and with
**email + password**. Email login always works without any configuration; Google appears once the OAuth values
below are set (until then the Google button is greyed out with "not set up"). Without an account the app still
works (top bar "Sign in · Guest") and no evaluation is ever blocked.

## Pages and routes

| Path | What |
| --- | --- |
| `/start` | Landing page (hero with logo, features) |
| `/tarife` | Pricing: Free · Pro · Company with evaluations per month, monthly/yearly switch |
| `/konto` | Sign in or create an account (Google, email + password), plan, usage bar, Stripe portal, sign out |
| `/admin` | Unlock company plans by hand (name, seats, expiry, members), list accounts. Allowed for `ADMIN_EMAILS` or with the developer code (`DEV_OPTIONS_CODE`, default 2211) |
| `/api/auth/*` | Auth.js (NextAuth v5), JWT sessions |
| `/api/saas/registrieren` | Create an email + password account (scrypt hash, at least 8 characters) and send the confirmation link |
| `/api/saas/bestaetigen` · `/bestaetigung-erneut` | Confirm the email from the link (`/konto/bestaetigen`), send a new link |
| `/api/saas/passwort-vergessen` · `/passwort-neu` | Email a reset link (`/konto/passwort-neu`), set the new password |
| `/api/saas/me` | Current account, plan, quota, which features are configured |
| `/api/saas/usage` | +1 evaluation (called when an evaluation starts; soft quota, never refuses) |
| `/api/saas/checkout` · `/portal` · `/sync` | Stripe Checkout, Customer Portal, read subscription after checkout |
| `/api/saas/webhook` | Stripe webhook (`checkout.session.completed`, `customer.subscription.*`), signature checked |
| `/api/saas/admin` | Admin list and company grants |

Code: `web/lib/saas/` (plans and quota rules in `plaene.ts`, tested in `web/lib/saas.test.mjs`),
UI in `web/components/saas/`. Data: `web/.data/saas.json` (git-ignored; folder via `LV_SCOUT_DATA_DIR`).
Passwords are stored only as scrypt hashes (`web/lib/saas/passwort.ts`, random salt, `timingSafeEqual`), never
in plain text and never sent to the browser. An address that already signed in with Google cannot be registered
with a password (no takeover); an existing password account cannot be registered twice.

### Email accounts: confirmation, password reset, fixed account

- **Register → confirm → sign in:** after registering, LV Scout emails a confirmation link (valid 24 h). Signing in
  with email + password works only after the link was opened; the sign-in page offers "Send confirmation link again".
- **Forgot password:** "Forgot password?" on `/konto` emails a reset link (valid 1 h, works once). Opening it also
  confirms the email.
- Tokens are random (32 bytes); only their SHA-256 hash and expiry are stored in `saas.json`.
- **Mail delivery** uses SMTP (nodemailer), configured only by env in `web/.env.local`:

  | Variable | Gmail example |
  | --- | --- |
  | `SMTP_HOST` | `smtp.gmail.com` |
  | `SMTP_PORT` | `465` (TLS) |
  | `SMTP_USER` | the Gmail address |
  | `SMTP_PASS` | a Google **app password** (Google account → Security → 2-Step Verification → App passwords), not the normal password |
  | `MAIL_FROM` | e.g. `LV Scout <name@gmail.com>` (defaults to `SMTP_USER`) |

  Without `SMTP_HOST` no mail is sent and the UI shows nothing special: the link is written to the server log only
  (`[mail] SMTP not configured …` in `/tmp/boq-app.log` when started with `tools/dev.py`).
- **Fixed account:** `dummy@gmail.com` / `12345` always exists and is pre-confirmed (created at server start when
  missing, `web/lib/saas/seed.ts`; the 8-character minimum does not apply to it). It uses the normal sign-in form.
- **Google** stays in *Testing* mode (publishing needs a verified domain): only the test users entered on the
  consent screen can sign in with Google.

## Plans

| Plan | Quota | Price (test mode) | Stripe lookup key |
| --- | --- | --- | --- |
| Free | 3 evaluations / month | 0 € | – |
| Pro | 50 evaluations / month | 29 € / month · 290 € / year | `lv_scout_pro_monthly`, `lv_scout_pro_yearly` |
| Company | 200 evaluations / seat / month | 49 € / seat / month · 490 € / seat / year | `lv_scout_company_seat_monthly`, `lv_scout_company_seat_yearly` |

Effective plan: active company grant (admin or Stripe Company) → active Pro subscription → Free. Not signed in = Guest (unlimited).
The quota is soft: a banner with an upgrade button appears above the upload when 1 or 0 evaluations are left.

Products and prices exist in **Stripe test mode on the existing account "Print Pool"** (metadata `app=lv-scout`).
The app looks prices up by lookup key, so no price IDs need to be configured.

## Activate

Put the values in `.env.local` in the repository root (or `web/.env.local`), never in commits, issues or chat:

1. **Google login** (step by step):
   1. Open <https://console.cloud.google.com/>, pick or create a project (e.g. "LV Scout").
   2. *APIs & Services → OAuth consent screen* (Google Auth Platform → Branding/Audience): app name "LV Scout",
      your support email, user type **External**, publishing status **Testing**; under *Test users* add every
      Google account that should sign in.
   3. *APIs & Services → Credentials → Create credentials → OAuth client ID*, application type **Web application**,
      name e.g. "LV Scout local".
   4. *Authorized JavaScript origins*: `http://localhost:3000`. *Authorized redirect URIs*:
      `http://localhost:3000/api/auth/callback/google` (for a hosted app add `https://<host>/api/auth/callback/google`
      and set `APP_URL`).
   5. Create, then **Download JSON** (`client_secret_….json`).
   6. Write the values into `web/.env.local`: `python3 tools/google_oauth_env.py ~/Downloads/client_secret_….json`.
      It sets `AUTH_GOOGLE_ID` and `AUTH_GOOGLE_SECRET`, adds a random `AUTH_SECRET` and `APP_URL=http://localhost:3000`
      when missing, keeps every other line and prints only `ok`. Delete the JSON afterwards.
   7. Restart (`python3 tools/dev.py`); `/konto` now shows an active "Continue with Google".
2. **Stripe:** `STRIPE_SECRET_KEY=sk_test_…` from Print Pool (Dashboard → Developers → API keys, test mode).
   Checkout then works; after paying, `/konto?checkout=ok` reads the subscription directly from Stripe, so a
   webhook is not required locally. For live updates (cancellations, renewals):
   `stripe listen --forward-to localhost:3000/api/saas/webhook` and set the printed `STRIPE_WEBHOOK_SECRET`.
   The Customer Portal configuration already exists in test mode (`bpc_1UePYIE6CuZdLn5LVFNjC77b`, default): cancel at period end, switch Pro/Company and seats, invoices, card.
3. **Admin:** `ADMIN_EMAILS=you@example.com` or open `/admin` with the developer code.

Restart `python3 tools/dev.py` after changing the variables. Test card: `4242 4242 4242 4242`, any future date, any CVC.
