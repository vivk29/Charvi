import { Dashboard } from "@/components/dashboard";
import { createClient } from "@/lib/supabase/server";

export default async function Home() {
  const supabase = await createClient();
  let initialEmail: string | null = null;

  if (supabase) {
    const { data } = await supabase.auth.getClaims();
    const emailClaim = data?.claims?.email;
    if (typeof emailClaim === "string") {
      initialEmail = emailClaim;
    }
  }

  return <Dashboard initialEmail={initialEmail} />;
}
