-- Intro price (Rs 599 first Pro month): count completed Pro purchases so the offer is used once.
-- Safe to re-run. Existing users who ever had Pro are marked as having purchased.
alter table public.profiles add column if not exists pro_purchases int not null default 0;
update public.profiles set pro_purchases = 1 where pro_purchases = 0 and pro_until is not null;
