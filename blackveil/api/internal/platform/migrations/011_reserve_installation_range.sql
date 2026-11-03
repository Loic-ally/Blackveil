SELECT setval('legacy_tenant_numbers',
              GREATEST(4199, (SELECT last_value FROM legacy_tenant_numbers)),
              true);
