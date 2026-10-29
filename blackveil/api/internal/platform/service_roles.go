package platform

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

type databaseRole struct {
	name     string
	password string
}

func migrate(ctx context.Context) error {
	pool, err := pgxpool.New(ctx, env("DATABASE_URL", "postgres://aether:aether-dev-only@aether-db:5432/aether?sslmode=disable"))
	if err != nil {
		return err
	}
	defer pool.Close()
	if err = pool.Ping(ctx); err != nil {
		return err
	}
	roles := []databaseRole{
		{name: "aether_api", password: env("AETHER_API_DB_PASSWORD", "")},
		{name: "aether_auth", password: env("AETHER_AUTH_DB_PASSWORD", "")},
		{name: "aether_worker", password: env("AETHER_WORKER_DB_PASSWORD", "")},
		{name: "aether_legacy", password: env("AETHER_LEGACY_DB_PASSWORD", "")},
		{name: "aether_telemetry", password: env("AETHER_TELEMETRY_DB_PASSWORD", "")},
	}
	for _, role := range roles {
		if len(role.password) < 64 {
			return fmt.Errorf("database credential for %s must be at least 64 characters", role.name)
		}
		var statement string
		if err = pool.QueryRow(ctx, `SELECT format(
			'CREATE ROLE %I LOGIN PASSWORD %L', $1::text, $2::text
		) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=$1::text)
		UNION ALL
		SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)
		WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname=$1::text)`, role.name, role.password).Scan(&statement); err != nil {
			return fmt.Errorf("prepare database role %s: %w", role.name, err)
		}
		if _, err = pool.Exec(ctx, statement); err != nil {
			return fmt.Errorf("configure database role %s: %w", role.name, err)
		}
	}
	return applyMigrations(ctx, pool)
}
