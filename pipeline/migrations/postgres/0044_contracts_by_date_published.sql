-- The portal's contract list, in the order it asks for it.
--
-- The port of ../0044_contracts_by_date_published.sql; that file carries the
-- measurement and the argument for paying an index's write cost here.
--
-- One difference, and it is the reason this is not a copy. SQLite sorts NULLs
-- last under `DESC` and PostgreSQL sorts them first, so an index written the
-- same way in both trees would order the public contracts list differently
-- depending on which backend answered -- and would not be used at all by a
-- query asking for the other order. `NULLS LAST` here matches what SQLite
-- does by default, so the two backends agree, and matches the explicit
-- `NULLS LAST` the portal's own ORDER BY now carries, so the planner can use
-- it.
CREATE INDEX IF NOT EXISTS idx_contracts_date_published
    ON contracts (date_published DESC NULLS LAST, notice_id);
