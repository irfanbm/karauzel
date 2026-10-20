# Supabase setup

1. Create a project at https://supabase.com/dashboard.
2. Copy Project URL and API keys from **Project Settings → API** into `.env` using `.env.example`.
3. Run `supabase/schema.sql` in **SQL Editor → New query**.
4. Enable Email under **Authentication → Providers → Email**.
5. Enable Google under **Authentication → Providers → Google**. Use `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback` as the OAuth callback.

The anon key may be used in the browser. The service-role key is server-only and must never be committed.
