-- Exam families: separate Streamlit apps (mgmt_law, sarkari, medical, engineering) on one Supabase project.
-- 1) Pro + the first-ever intro offer are tracked per app in public.pro_entitlements.
-- 2) Attempts are tagged with exam_family so each app shows only its own progress.
-- Safe to re-run. Run once in Supabase -> SQL Editor (after 2026-10-27_pro_purchases.sql).

create table if not exists public.pro_entitlements (
  user_id              text not null references public.profiles(user_id) on delete cascade,
  exam_family          text not null check (exam_family in ('mgmt_law','sarkari','medical','engineering')),
  pro_until            date,
  pro_purchases        int  not null default 0,
  pending_payment_ref  text,
  updated_at           timestamptz not null default now(),
  primary key (user_id, exam_family)
);

-- Same policy as profiles/attempts: RLS on, no policies, so only the server-side service_role key can access it.
alter table public.pro_entitlements enable row level security;
revoke all on public.pro_entitlements from anon, authenticated;

-- Backfill: existing Pro (and intro-offer usage) belongs to the original CAT/CLAT/IPMAT app.
insert into public.pro_entitlements (user_id, exam_family, pro_until, pro_purchases, pending_payment_ref)
select user_id, 'mgmt_law', pro_until,
       greatest(coalesce(pro_purchases, 0), case when pro_until is not null then 1 else 0 end),
       pending_payment_ref
from public.profiles
where pro_until is not null or coalesce(pro_purchases, 0) > 0 or pending_payment_ref is not null
on conflict (user_id, exam_family) do nothing;

-- Tag attempts by app. Existing rows get the default 'mgmt_law' (backfill happens via the default).
alter table public.attempts add column if not exists exam_family text not null default 'mgmt_law';
update public.attempts set exam_family = 'mgmt_law' where exam_family is null;
create index if not exists attempts_user_family_idx on public.attempts(user_id, exam_family, created_at);
