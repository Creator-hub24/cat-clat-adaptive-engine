-- CAT/CLAT Adaptive Engine: privacy-first schema.
-- user_id is an HMAC-SHA256 hash of the lowercased email (secret pepper). No email/name/photo columns exist.

create table if not exists public.profiles (
  user_id              text primary key check (char_length(user_id) = 64),
  streak               int  not null default 0,
  best_streak          int  not null default 0,
  usage_day            date,
  ai_used              int  not null default 0,
  plan                 text not null default 'free' check (plan in ('free','pro')),
  pro_until            date,
  review_queue         jsonb not null default '{}'::jsonb,
  pending_payment_ref  text,
  updated_at           timestamptz not null default now()
);

create table if not exists public.attempts (
  id           bigint generated always as identity primary key,
  user_id      text not null references public.profiles(user_id) on delete cascade,
  question_id  text not null,
  topic        text not null,
  difficulty   text not null,
  correct      boolean not null,
  trap_type    text,
  created_at   timestamptz not null default now()
);
create index if not exists attempts_user_idx on public.attempts(user_id, created_at);

-- Row Level Security ON with NO policies: the public anon key can read/write nothing.
-- Only the service_role key (kept server-side in Streamlit secrets) bypasses RLS.
alter table public.profiles enable row level security;
alter table public.attempts enable row level security;
revoke all on public.profiles, public.attempts from anon, authenticated;
