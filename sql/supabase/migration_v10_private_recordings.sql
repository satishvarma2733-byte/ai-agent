-- Make call recordings private (run once in the Supabase SQL editor).
-- The API serves recordings through signed links from then on; no data change is needed,
-- because rows holding the old public URL are mapped by the API as well.

UPDATE storage.buckets SET public = false WHERE id = 'call-recordings';

-- Let anyone, including holders of the public anon key, read and list every recording.
DROP POLICY IF EXISTS "Public read recordings" ON storage.objects;

-- Let anyone upload into the bucket. The service role and S3 access keys used by the
-- recording egress bypass row-level security, so nothing legitimate needs this policy.
DROP POLICY IF EXISTS "Service role write recordings" ON storage.objects;

-- The consolidated setup.sql from May 2026 created this one instead: anyone could upload into the bucket.
DROP POLICY IF EXISTS "Allow recordings upload" ON storage.objects;
