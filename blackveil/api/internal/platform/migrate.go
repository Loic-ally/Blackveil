package platform

import (
	"context"
	"github.com/jackc/pgx/v5/pgxpool"
)

func applyMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `SELECT pg_advisory_xact_lock(74190821)`); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())`); err != nil {
		return err
	}
	files, err := migrationFiles.ReadDir("migrations")
	if err != nil {
		return err
	}
	for _, file := range files {
		var applied bool
		if err = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name=$1)`, file.Name()).Scan(&applied); err != nil {
			return err
		}
		if applied {
			continue
		}
		schema, readErr := migrationFiles.ReadFile("migrations/" + file.Name())
		if readErr != nil {
			return readErr
		}
		if _, err = tx.Exec(ctx, string(schema)); err != nil {
			return err
		}
		if _, err = tx.Exec(ctx, `INSERT INTO schema_migrations(name) VALUES($1)`, file.Name()); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}
