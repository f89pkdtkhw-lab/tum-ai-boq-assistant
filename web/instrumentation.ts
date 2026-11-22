// Runs once when the Next server starts: make sure the fixed email account exists (lib/saas/seed.ts).
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { seedKonto } = await import("./lib/saas/seed");
  await seedKonto();
}
