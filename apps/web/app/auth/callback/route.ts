import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const requestedNext = requestUrl.searchParams.get("next") || "/";
  const nextPath =
    requestedNext.startsWith("/") && !requestedNext.startsWith("//")
      ? requestedNext
      : "/";
  const destination = new URL(nextPath, requestUrl.origin);

  if (!code) {
    destination.searchParams.set("auth", "error");
    return NextResponse.redirect(destination);
  }

  const supabase = await createClient();
  if (!supabase) {
    destination.searchParams.set("auth", "error");
    return NextResponse.redirect(destination);
  }

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    destination.searchParams.set("auth", "error");
    return NextResponse.redirect(destination);
  }

  if (!destination.searchParams.has("auth")) {
    destination.searchParams.set(
      "auth",
      nextPath.startsWith("/reset-password") ? "recovery" : "confirmed",
    );
  }
  return NextResponse.redirect(destination);
}
