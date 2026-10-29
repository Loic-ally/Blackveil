ALTER TABLE reports
    ADD COLUMN lease_until TIMESTAMPTZ,
    ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0);

-- Reports claimed before leases existed cannot be safely distinguished from
-- abandoned work, so return them to the durable queue during this migration.
UPDATE reports SET status='queued' WHERE status='running';

CREATE INDEX reports_claimable_idx
    ON reports(status, lease_until, created_at)
    WHERE status IN ('queued', 'running');
