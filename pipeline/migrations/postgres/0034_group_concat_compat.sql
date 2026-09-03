-- GROUP_CONCAT, so that nine export queries can stay one query each.
--
-- SQLite has GROUP_CONCAT and PostgreSQL has string_agg. They are the same
-- aggregate with different names, and for the two-argument form the argument
-- order is identical too. Nine places in pipeline/exports/ call GROUP_CONCAT
-- from application SQL -- exports/schema.py (5), exports/geojson.py (2),
-- exports/echarts.py (1), exports/provenance.py (1).
--
-- The alternative was writing those nine queries twice, once per backend.
-- That is the same trade this project already took for parameter placeholders
-- (see pipeline/sqldialect.py): a query that exists twice is a query that will
-- eventually differ in one copy, and the difference will be found by somebody
-- reading an export that disagrees with the portal. So the name is defined
-- here instead, and the nine queries stay one query each.
--
-- SQLite 3.44 added `string_agg` as an alias for GROUP_CONCAT, which would
-- have solved this from the other direction and needed nothing here. This
-- machine has 3.40.1, and the version of SQLite a contributor gets is
-- whatever their Python bundles -- not something this project can require.
-- Revisit when the floor is 3.44.
--
-- Views are NOT written this way: migrations 0024 and 0025 call `string_agg`
-- directly, because a view is defined once per dialect anyway, so there is no
-- duplicated query to avoid and no reason to prefer a shim over the native
-- aggregate. This exists for SQL that has to read the same on both backends.
--
-- NULL handling matches SQLite: a NULL value is skipped rather than ending
-- the string or becoming the text 'NULL'. That is what SQLite's GROUP_CONCAT
-- does, and it is what array_to_string and string_agg do, so all three agree.
--
-- Performance: this concatenates rather than appending to a buffer, so it is
-- quadratic in the number of values where string_agg is linear. It is used on
-- groups of successor codes, previous company names, provider mentions and
-- concern terms -- tens of values, not thousands. If a caller ever needs it
-- on a large group, that caller should use string_agg directly and say why.

-- Two-argument form: GROUP_CONCAT(value, separator).
CREATE OR REPLACE FUNCTION _group_concat_trans(state text, value text, separator text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN value IS NULL THEN state
        WHEN state IS NULL THEN value
        ELSE state || separator || value
    END;
$$;

CREATE OR REPLACE AGGREGATE group_concat(text, text) (
    SFUNC  = _group_concat_trans,
    STYPE  = text
);

-- One-argument form: GROUP_CONCAT(value), comma-separated, which is what
-- SQLite's single-argument form does. Used with DISTINCT at two call sites;
-- DISTINCT works on any aggregate in PostgreSQL, so nothing extra is needed
-- for it. The order of the values is unspecified in both engines.
CREATE OR REPLACE FUNCTION _group_concat_trans(state text, value text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN value IS NULL THEN state
        WHEN state IS NULL THEN value
        ELSE state || ',' || value
    END;
$$;

CREATE OR REPLACE AGGREGATE group_concat(text) (
    SFUNC  = _group_concat_trans,
    STYPE  = text
);
