# Combating Drugs Partnership document candidates

Each row is a link that *looked* like a CDP strategy, needs assessment or
outcomes framework. **None of it is in the evidence base yet.** Open each
one, and mark the good ones verified:

```sql
UPDATE cdp_document_candidates SET verified = 1, verified_at = datetime('now')
 WHERE authority_ons_code = 'E10000016' AND candidate_url = '...';
```

Confidence counts matching signals (vocabulary, substance hint, file type).
It is a triage aid, not a probability, and does not mean a document is what
its link text claims.

*No candidates discovered. Check authority_websites.py coverage.*
