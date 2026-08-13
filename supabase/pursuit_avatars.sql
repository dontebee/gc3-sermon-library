-- Pursuit: faces on the cards. PD's decision.
--
-- Planning Center People carries an avatar URL per person (their public
-- CDN) and a child flag. The People sync fills both. The board renders
-- the photo when there is one and falls back to the initials avatar when
-- there is not, or when the image fails to load.
--
-- Two lines the interface holds:
--   - Children's photos never render on the board. Kids do not board
--     ships (households roll up), and is_child is how the UI makes sure
--     of it even if a child record ever gains a card.
--   - Photos appear only inside the role-gated tool, the same faces staff
--     already see in PCO itself. Nothing here is exported or public.

alter table pursuit_people
  add column if not exists avatar_url text;
alter table pursuit_people
  add column if not exists is_child boolean not null default false;
