-- CUET app: allow exam_family = 'cuet' in public.pro_entitlements (its own Pro and first-month offer).
-- The CHECK in 2026-10-28_exam_families.sql listed only mgmt_law, sarkari, medical and engineering, so a CUET
-- Pro row would be rejected. Until this runs, the CUET app shows "Pro coming soon (database setup pending)".
-- attempts, usage_guard, abuse_events and consumed_payments have no family check: nothing else to change.
-- Safe to re-run. Run once in Supabase -> SQL Editor (after 2026-10-28_exam_families.sql).

alter table public.pro_entitlements drop constraint if exists pro_entitlements_exam_family_check;
alter table public.pro_entitlements add constraint pro_entitlements_exam_family_check
  check (exam_family in ('mgmt_law','sarkari','cuet','medical','engineering'));
