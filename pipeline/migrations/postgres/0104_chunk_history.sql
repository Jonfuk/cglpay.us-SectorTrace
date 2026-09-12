-- Preserve prior chunk text when a deterministic re-chunk changes the output
-- for the same document/parser version.  One active chunk may occupy a given
-- ordinal, while content-addressed historical rows remain queryable.

DO $$
DECLARE
    constraint_name name;
BEGIN
    SELECT con.conname
      INTO constraint_name
      FROM pg_constraint con
     WHERE con.conrelid = 'document_chunks'::regclass
       AND con.contype = 'u'
       AND (
           SELECT array_agg(att.attname ORDER BY key.ordinality)
             FROM unnest(con.conkey) WITH ORDINALITY AS key(attnum, ordinality)
             JOIN pg_attribute att
               ON att.attrelid = con.conrelid AND att.attnum = key.attnum
       ) = ARRAY['document_version_id', 'chunker_name', 'chunker_version', 'chunk_index']::name[];
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE document_chunks DROP CONSTRAINT %I', constraint_name);
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_chunks_one_active_ordinal
    ON document_chunks (document_version_id, chunker_name, chunker_version, chunk_index)
    WHERE superseded = 0;
