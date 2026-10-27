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

-- v0.3: adaptive levels, timing, anonymous question reports (safe to re-run on an existing project)
alter table public.profiles add column if not exists topic_levels jsonb not null default '{}'::jsonb;
alter table public.attempts add column if not exists time_taken_s int;
alter table public.attempts add column if not exists timing_class text;

create table if not exists public.question_reports (
  id            bigint generated always as identity primary key,
  topic         text not null,
  question_ref  text not null,   -- seed id or content hash of an AI question; NO user identifier
  reason        text not null,
  created_at    timestamptz not null default now()
);
alter table public.question_reports enable row level security;
revoke all on public.question_reports from anon, authenticated;

-- v0.4: intro price marker (see supabase/migrations/2026-10-27_pro_purchases.sql)
alter table public.profiles add column if not exists pro_purchases int not null default 0;

-- v0.5: exam families (see supabase/migrations/2026-10-28_exam_families.sql)
create table if not exists public.pro_entitlements (
  user_id              text not null references public.profiles(user_id) on delete cascade,
  exam_family          text not null check (exam_family in ('mgmt_law','sarkari','medical','engineering')),
  pro_until            date,
  pro_purchases        int  not null default 0,
  pending_payment_ref  text,
  updated_at           timestamptz not null default now(),
  primary key (user_id, exam_family)
);
alter table public.pro_entitlements enable row level security;
revoke all on public.pro_entitlements from anon, authenticated;
alter table public.attempts add column if not exists exam_family text not null default 'mgmt_law';
create index if not exists attempts_user_family_idx on public.attempts(user_id, exam_family, created_at);

-- ---- Fair use: Pro AI cap (IST day), speed-check cooldown, one active session per (user, exam_family)
create table if not exists public.usage_guard (
  user_id text not null references public.profiles(user_id) on delete cascade,
  exam_family text not null default 'mgmt_law',
  session_token text,
  session_started_at timestamptz,
  ai_day date,
  ai_used int not null default 0,
  cooldown_until timestamptz,
  updated_at timestamptz not null default now(),
  primary key (user_id, exam_family)
);
alter table public.usage_guard enable row level security;
revoke all on public.usage_guard from anon, authenticated;

create table if not exists public.abuse_events (
  id bigint generated always as identity primary key,
  user_id text not null references public.profiles(user_id) on delete cascade,
  exam_family text not null default 'mgmt_law',
  kind text not null,
  detail text,
  created_at timestamptz not null default now()
);
create index if not exists abuse_events_user_idx on public.abuse_events (user_id, exam_family, created_at desc);
alter table public.abuse_events enable row level security;
revoke all on public.abuse_events from anon, authenticated;
