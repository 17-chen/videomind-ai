import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { isSupabaseConfigured, supabaseAnonKey, supabaseUrl } from "@/lib/supabase/config";

export async function getServerAccessToken(): Promise<string | undefined> {
  if (!isSupabaseConfigured) return undefined;
  const cookieStore = await cookies();
  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (values) => {
        try {
          values.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Server Components cannot always write refreshed cookies.
        }
      }
    }
  });
  const { data: claims, error } = await supabase.auth.getClaims();
  if (error || !claims?.claims) return undefined;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token;
}
