-- Founding 500 launch offer: record which plan each Razorpay payment bought, so each app can count
-- how many of its 500 Rs 199 launch seats are taken. Safe to re-run.
alter table public.consumed_payments add column if not exists plan text;
create index if not exists consumed_payments_family_plan_idx on public.consumed_payments (exam_family, plan);
