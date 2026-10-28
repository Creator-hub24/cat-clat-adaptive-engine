-- Each Razorpay payment link / payment ref extends Pro at most once (replay + double-click/two-session race).
-- The app inserts here BEFORE extending Pro; a unique violation means it was already applied.
-- user_id is nullable and has no FK so the record survives (as an anonymous ref) and never blocks inserts.
create table if not exists public.consumed_payments (
  payment_ref text primary key,
  user_id     text,
  exam_family text not null default 'mgmt_law',
  created_at  timestamptz not null default now()
);
create index if not exists consumed_payments_user_idx on public.consumed_payments (user_id);
alter table public.consumed_payments enable row level security;
revoke all on public.consumed_payments from anon, authenticated;
