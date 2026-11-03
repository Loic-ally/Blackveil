ALTER TABLE reports
    ADD COLUMN lease_until TIMESTAMPTZ,
    ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0);

UPDATE reports SET status='queued' WHERE status='running';

CREATE INDEX reports_claimable_idx
    ON reports(status, lease_until, created_at)
    WHERE status IN ('queued', 'running');
