"""A local web interface for reading the warehouse and clearing the review queue.

Two things the CLI cannot do well, and nothing else:

  * **Look at the database.** `sqlite3 data/warehouse.db` works, but the
    schema is 50-odd tables and views across 26 migrations, and the questions
    people actually have ("what is in here", "what did m10 find") are browsing
    questions, not query-writing ones.

  * **Decide review items.** 2,000+ rows accumulate in `review_queue` that no
    module can resolve, and until now there was no way to say "yes, that
    match is right" or "no, ignore that one" other than editing the table by
    hand — which left no trace of who decided or why.

The split across this package mirrors a split in what the two jobs are allowed
to do. `queries` runs on a connection opened `mode=ro`, so browsing cannot
write to the warehouse even if a query tries; `review` is the only module here
that opens a writable connection, and the only rows it ever writes are the
item's status and its decision record. Nothing in this package collects,
parses, or promotes anything.
"""
