-- Reserve installation identifiers 4100–4199 for migration fixtures (the
-- platform operator 4100, the North Works/Harbor archives 4101/4102, and the
-- recovery/enrollment receipts keyed on them). The tenant-number sequence starts
-- at 4100 and the two seeded tenants consume 4100/4101, so without this a freshly
-- registered workspace would receive 4102+ and collide with a seeded installation
-- number — which the Stage 03 migration-history lookup keys on, leaking a seeded
-- tenant's record as the caller's "own" (including in patched mode). Advance the
-- sequence past the reserved block so real workspaces start at 4200.
SELECT setval('legacy_tenant_numbers',
              GREATEST(4199, (SELECT last_value FROM legacy_tenant_numbers)),
              true);
