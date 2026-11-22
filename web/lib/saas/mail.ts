// Outgoing mail for email accounts (confirmation, password reset) via SMTP (nodemailer).
// Configured only by env in web/.env.local: SMTP_HOST, SMTP_PORT (465 = TLS, e.g. smtp.gmail.com with an app
// password), SMTP_USER, SMTP_PASS, MAIL_FROM. Without SMTP_HOST nothing is sent: the link goes to the server log only.
import nodemailer from "nodemailer";

export function smtpAktiv(): boolean {
  return Boolean(process.env.SMTP_HOST);
}

export async function sendeMail(an: string, betreff: string, text: string, link: string): Promise<void> {
  if (!smtpAktiv()) {
    console.log(`[mail] SMTP not configured – "${betreff}" for ${an}: ${link}`);
    return;
  }
  const port = Number(process.env.SMTP_PORT || 465);
  const transport = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port,
    secure: port === 465,
    auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS ?? "" } : undefined,
  });
  const von = process.env.MAIL_FROM || process.env.SMTP_USER || "no-reply@localhost";
  try {
    await transport.sendMail({ from: von, to: an, subject: betreff, text });
  } catch (err) {
    // Never log credentials; the link is logged so a local admin can still help.
    console.error(`[mail] sending "${betreff}" to ${an} failed: ${err instanceof Error ? err.message : String(err)}. Link: ${link}`);
    throw new Error("The email could not be sent.");
  }
}

export function bestaetigungsMail(link: string): { betreff: string; text: string } {
  return {
    betreff: "LV Scout: confirm your email / E-Mail bestätigen",
    text: `Hello,\n\nplease confirm your email address for LV Scout (valid for 24 hours):\n${link}\n\n`
      + `Hallo,\n\nbitte bestätige deine E-Mail-Adresse für LV Scout (24 Stunden gültig):\n${link}\n\n`
      + "If you did not sign up, ignore this email. / Falls du dich nicht registriert hast, ignoriere diese E-Mail.\n",
  };
}

export function resetMail(link: string): { betreff: string; text: string } {
  return {
    betreff: "LV Scout: reset your password / Passwort zurücksetzen",
    text: `Hello,\n\nuse this link to set a new LV Scout password (valid for 1 hour):\n${link}\n\n`
      + `Hallo,\n\nmit diesem Link setzt du ein neues LV-Scout-Passwort (1 Stunde gültig):\n${link}\n\n`
      + "If you did not ask for this, ignore this email. / Falls du das nicht angefordert hast, ignoriere diese E-Mail.\n",
  };
}
