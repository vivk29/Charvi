import { Dashboard } from "@/components/dashboard";
import { createClient } from "@/lib/supabase/server";

export default async function Home() {
  const supabase = await createClient();
  let initialEmail: string | null = null;

  if (supabase) {
    const { data } = await supabase.auth.getClaims();
    if (typeof data?.claims?.email === "string") {
      initialEmail = data.claims.email;
    }
  }

  return <Dashboard initialEmail={initialEmail} />;
}
