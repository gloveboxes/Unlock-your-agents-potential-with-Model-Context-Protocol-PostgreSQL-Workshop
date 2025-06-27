#!/bin/bash
set -e

echo "🚀 Initializing Zava PostgreSQL Database..."

# Create the zava database
echo "📦 Creating 'zava' database..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE zava;
    GRANT ALL PRIVILEGES ON DATABASE zava TO $POSTGRES_USER;
EOSQL

# Install pgvector extension in the zava database
echo "🔧 Installing pgvector extension in 'zava' database..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "zava" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

# Check if backup file exists and restore it
BACKUP_FILE="/docker-entrypoint-initdb.d/backups/zava_retail_2025_05_27_postgres.backup"
echo "🔍 Checking for backup file at: $BACKUP_FILE"
echo "📁 Contents of backup directory:"
ls -la /docker-entrypoint-initdb.d/backups/ || echo "Backup directory not found"

if [ -f "$BACKUP_FILE" ]; then
    echo "📂 Found backup file, restoring data to 'zava' database..."
    pg_restore -v --username "$POSTGRES_USER" --dbname "zava" --clean --if-exists --no-owner --no-privileges "$BACKUP_FILE" || {
        echo "❌ pg_restore failed with exit code $?"
        echo "🔧 Trying alternative restore method..."
        # Try without --clean --if-exists flags
        pg_restore -v --username "$POSTGRES_USER" --dbname "zava" --no-owner --no-privileges "$BACKUP_FILE" || {
            echo "❌ Alternative restore method also failed"
            exit 1
        }
    }
    echo "✅ Database restoration completed!"
else
    echo "⚠️  Backup file not found at $BACKUP_FILE"
    echo "📋 Database 'zava' created but no data restored."
fi

echo "🎉 Zava PostgreSQL Database initialization completed!"
