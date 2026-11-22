import { redirect } from "next/navigation";

// The former display-test preview (synthetic example, invented prices) is not part of the app UI any more;
// Vorschau.tsx stays in the repo for developers. The route sends users to the start page.
export default function BerichtVorschauSeite() {
  redirect("/");
}
