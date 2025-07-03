#!/usr/bin/env python3
"""
AI-Friendly PostgreSQL Database Schema Tool

This script provides methods to query PostgreSQL database table schemas in AI-friendly formats
for dynamic query generation and AI model integration.

Usage:
    python sales_data_postgres.py

Requirements:
    - asyncpg (async PostgreSQL adapter)
    - asyncio (for async operations)
    - pandas (for structured JSON output)
    - python-dotenv (for environment variables)
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import asyncpg
import pandas as pd
from dotenv import load_dotenv

# Load environment variables (don't override existing ones)
load_dotenv(override=False)

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# PostgreSQL connection configuration
POSTGRES_CONFIG = {
    'host': os.getenv('postgres_host', 'db'),
    'port': int(os.getenv('postgres_port', '5432')),
    'user': os.getenv('postgres_user', 'postgres'),
    'password': os.getenv('postgres_password', 'P@ssw0rd!'),
    'database': os.getenv('postgres_db', 'zava')
}

SCHEMA_NAME = 'retail'

# Constants - table names without schema prefix (will be added in queries)
CUSTOMERS_TABLE = "customers"
PRODUCTS_TABLE = "products"
ORDERS_TABLE = "orders"
ORDER_ITEMS_TABLE = "order_items"
STORES_TABLE = "stores"
CATEGORIES_TABLE = "categories"
PRODUCT_TYPES_TABLE = "product_types"
INVENTORY_TABLE = "inventory"


class PostgreSQLSchemaProvider:
    """Provides PostgreSQL database schema information in AI-friendly formats for dynamic query generation."""

    def __init__(self, postgres_config: Optional[Dict] = None):
        self.postgres_config = postgres_config or POSTGRES_CONFIG
        self.connection: Optional[asyncpg.Connection] = None
        self.all_schemas: Optional[Dict[str, Dict[str, Any]]] = None
        self.schema_name = SCHEMA_NAME

    async def __aenter__(self):
        """Async context manager entry - just return self, don't auto-open connection."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close connection if it was opened."""
        await self.close_connection()

    async def open_connection(self):
        """Open PostgreSQL connection and preload schemas."""
        if self.connection is None:
            try:
                self.connection = await asyncpg.connect(**self.postgres_config)
                self.all_schemas = await self.get_all_schemas()
                logger.info(f"✅ PostgreSQL connection opened: {self.postgres_config['host']}:{self.postgres_config['port']}/{self.postgres_config['database']}")
            except Exception as e:
                logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
                raise

    async def close_connection(self):
        """Close PostgreSQL connection and cleanup."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.all_schemas = None
            logger.info("✅ PostgreSQL connection closed")

    def _get_qualified_table_name(self, table: str) -> str:
        """Get fully qualified table name with schema."""
        return f"{self.schema_name}.{table}"

    async def table_exists(self, table: str) -> bool:
        """Check if a table exists in the retail schema."""
        if not self.connection:
            return False
        
        result = await self.connection.fetchval(
            """SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = $1 AND table_name = $2
            )""",
            self.schema_name, table
        )
        return bool(result) if result is not None else False

    async def column_exists(self, table: str, column: str) -> bool:
        """Check if a column exists in the given table."""
        if not self.connection:
            return False
        
        result = await self.connection.fetchval(
            """SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_schema = $1 AND table_name = $2 AND column_name = $3
            )""",
            self.schema_name, table, column
        )
        return bool(result) if result is not None else False

    async def fetch_distinct_values(self, column: str, table: str) -> List[str]:
        """Return sorted list of distinct values for a given column in a table, after validation."""
        if not self.connection:
            raise ValueError("Database connection not established")
        if not await self.table_exists(table):
            raise ValueError(f"Table '{table}' does not exist in schema '{self.schema_name}'")
        if not await self.column_exists(table, column):
            raise ValueError(f"Column '{column}' does not exist in table '{self.schema_name}.{table}'")

        qualified_table = self._get_qualified_table_name(table)
        rows = await self.connection.fetch(
            f"SELECT DISTINCT {column} FROM {qualified_table} WHERE {column} IS NOT NULL ORDER BY {column}"
        )
        return [row[0] for row in rows if row[0]]

    def infer_relationship_type(self, references_table: str) -> str:
        """Infer a relationship type based on the referenced table."""
        return (
            "many_to_one"
            if references_table in {CUSTOMERS_TABLE, PRODUCTS_TABLE, STORES_TABLE, CATEGORIES_TABLE, PRODUCT_TYPES_TABLE, ORDERS_TABLE}
            else "one_to_many"
        )

    async def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Return schema information for a given table."""
        if not self.connection:
            return {"error": "Database connection not established"}

        if not await self.table_exists(table_name):
            return {"error": f"Table '{table_name}' not found in schema '{self.schema_name}'"}

        # Get column information
        columns = await self.connection.fetch(
            """SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns 
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position""",
            self.schema_name, table_name
        )

        # Get primary key information
        primary_keys = await self.connection.fetch(
            """SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = $1 
                AND tc.table_name = $2""",
            self.schema_name, table_name
        )
        
        pk_columns = set(row['column_name'] for row in primary_keys)

        # Get foreign key information
        foreign_keys = await self.connection.fetch(
            """SELECT 
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu 
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = $1 
                AND tc.table_name = $2""",
            self.schema_name, table_name
        )

        columns_format = ", ".join(f"{col['column_name']}:{col['data_type']}" for col in columns)
        lower_table = table_name.lower()

        # Define enum queries for each table to get unique values
        enum_queries = {
            STORES_TABLE: {
                "available_stores": ("store_name", STORES_TABLE)
            },
            CATEGORIES_TABLE: {
                "available_categories": ("category_name", CATEGORIES_TABLE)
            },
            PRODUCT_TYPES_TABLE: {
                "available_product_types": ("type_name", PRODUCT_TYPES_TABLE)
            },
            PRODUCTS_TABLE: {
                # Removed available_product_names to avoid lengthy output
            },
            ORDERS_TABLE: {
                "available_years": ("EXTRACT(YEAR FROM order_date)::text", ORDERS_TABLE)
            },
            ORDER_ITEMS_TABLE: {
                # "price_range": ("unit_price", ORDER_ITEMS_TABLE)
            }
        }

        enum_data = {}
        if lower_table in enum_queries:
            for key, (column, table) in enum_queries[lower_table].items():
                try:
                    if key == "price_range":
                        # For price range, get min and max values
                        qualified_table = self._get_qualified_table_name(table)
                        result = await self.connection.fetchrow(
                            f"SELECT MIN({column}) as min_price, MAX({column}) as max_price FROM {qualified_table}"
                        )
                        if result and result['min_price'] is not None:
                            enum_data[key] = f"${result['min_price']:.2f} - ${result['max_price']:.2f}"
                    elif key == "available_years":
                        # Handle years specially
                        qualified_table = self._get_qualified_table_name(table)
                        rows = await self.connection.fetch(
                            f"SELECT DISTINCT {column} as year FROM {qualified_table} WHERE order_date IS NOT NULL ORDER BY year"
                        )
                        years = [str(row['year']) for row in rows if row['year']]
                        enum_data[key] = years
                    else:
                        enum_data[key] = await self.fetch_distinct_values(column, table)
                except Exception as e:
                    logger.debug(f"Failed to fetch {key} for {table}: {e}")
                    enum_data[key] = []

        schema_data = {
            "table_name": table_name,
            "description": f"Table containing {table_name} data",
            "columns_format": columns_format,
            "columns": [
                {
                    "name": col['column_name'],
                    "type": col['data_type'],
                    "primary_key": col['column_name'] in pk_columns,
                    "required": col['is_nullable'] == 'NO',
                    "default_value": col['column_default'],
                }
                for col in columns
            ],
            "foreign_keys": [
                {
                    "column": fk['column_name'],
                    "references_table": fk['foreign_table_name'],
                    "references_column": fk['foreign_column_name'],
                    "description": f"{fk['column_name']} links to {fk['foreign_table_name']}.{fk['foreign_column_name']}",
                    "relationship_type": self.infer_relationship_type(fk['foreign_table_name']),
                }
                for fk in foreign_keys
            ],
        }

        schema_data.update(enum_data)
        return schema_data

    async def get_all_table_names(self) -> List[str]:
        """Get all user-defined table names in the retail schema."""
        if not self.connection:
            return []
        
        rows = await self.connection.fetch(
            """SELECT table_name FROM information_schema.tables 
               WHERE table_schema = $1 AND table_type = 'BASE TABLE'
               ORDER BY table_name""",
            self.schema_name
        )
        return [row['table_name'] for row in rows]

    async def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Get schema metadata for all tables."""
        table_names = await self.get_all_table_names()
        result = {}
        for table_name in table_names:
            result[table_name] = await self.get_table_schema(table_name)
        return result

    def format_schema_metadata_for_ai(self, schema: Dict[str, Any]) -> str:
        """Format schema data into an AI-readable format."""
        if "error" in schema:
            return f"**ERROR:** {schema['error']}"

        lines = [f"# Table: {self.schema_name}.{schema['table_name']}", ""]
        lines.append(
            f"**Purpose:** {schema.get('description', 'No description available')}"
        )
        lines.append("\n## Schema")
        lines.append(schema.get("columns_format", "N/A"))

        if schema.get("foreign_keys"):
            lines.append("\n## Relationships")
            for fk in schema["foreign_keys"]:
                lines.append(
                    f"- `{fk['column']}` → `{self.schema_name}.{fk['references_table']}.{fk['references_column']}` ({fk['relationship_type'].upper()})"
                )

        enum_fields = [
            ("available_stores", "Valid Stores"),
            ("available_categories", "Valid Categories"), 
            ("available_product_types", "Valid Product Types"),
            ("available_years", "Available Years"),
            ("price_range", "Price Range"),
        ]

        enum_lines = []
        for field_key, label in enum_fields:
            if schema.get(field_key):
                values = schema[field_key]
                # Always show the full list, no truncation
                enum_lines.append(
                    f"**{label}:** {', '.join(values) if isinstance(values, list) else values}"
                )

        if enum_lines:
            lines.append("\n## Valid Values")
            lines.extend(enum_lines)

        lines.append("\n## Query Hints")
        lines.append(
            f"- Use `{self.schema_name}.{schema['table_name']}` for queries about {schema['table_name'].replace('_', ' ')}"
        )
        if schema.get("foreign_keys"):
            for fk in schema["foreign_keys"]:
                lines.append(
                    f"- Join with `{self.schema_name}.{fk['references_table']}` using `{fk['column']}`"
                )

        return "\n".join(lines) + "\n"

    async def get_table_metadata_string(self, table_name: str) -> str:
        """Return formatted schema metadata string for a single table."""
        if self.all_schemas and table_name in self.all_schemas:
            return self.format_schema_metadata_for_ai(self.all_schemas[table_name])
        schema = await self.get_table_schema(table_name)
        return self.format_schema_metadata_for_ai(schema)

    async def execute_query(self, sql_query: str) -> str:
        """Execute a SQL query and return results in LLM-friendly JSON format."""
        if not self.connection:
            return json.dumps({"error": "Database connection not established"})

        # logger.info(f"\n🔍 Executing PostgreSQL query: {sql_query}\n")

        try:
            rows = await self.connection.fetch(sql_query)
            
            if not rows:
                return json.dumps({
                    "results": [],
                    "row_count": 0,
                    "columns": [],
                    "message": "The query returned no results. Try a different question."
                })

            # Convert asyncpg Records to list of dictionaries (much simpler!)
            results = [dict(row) for row in rows]
            columns = list(rows[0].keys()) if rows else []
            
            # Return LLM-friendly format
            return json.dumps({
                "results": results,
                "row_count": len(results),
                "columns": columns
            }, indent=2, default=str)

        except Exception as e:
            return json.dumps({
                "error": f"PostgreSQL query failed: {e!s}",
                "query": sql_query,
                "results": [],
                "row_count": 0,
                "columns": []
            })


async def test_connection() -> bool:
    """Test PostgreSQL connection and return success status."""
    try:
        conn = await asyncpg.connect(**POSTGRES_CONFIG)
        await conn.close()
        return True
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False


async def main() -> None:
    """Main function to run the schema tool."""
    logger.info("🤖 AI-Friendly PostgreSQL Database Schema Tool")
    logger.info("=" * 50)

    # Test connection first
    if not await test_connection():
        logger.error(f"❌ Error: Cannot connect to PostgreSQL at {POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}")
        logger.error("   Please verify:")
        logger.error("   1. PostgreSQL is running")
        logger.error("   2. Database 'zava' exists")
        logger.error("   3. Connection parameters in .env file are correct")
        logger.error("   4. User has access to the retail schema")
        return

    try:
        async with PostgreSQLSchemaProvider() as provider:
            # Explicitly open the database connection when needed
            await provider.open_connection()
            
            logger.info(f"\n📋 Getting all table schemas from {SCHEMA_NAME} schema...")
            if not provider.all_schemas:
                logger.warning(f"❌ No schemas available in {SCHEMA_NAME} schema")
                logger.warning("   Please run the PostgreSQL database generator first:")
                logger.warning("   python shared/database/data-generator/generate_zava_postgres.py")
                return

            logger.info("\n🧪 Testing SQL Query Execution:")
            logger.info("=" * 50)

            logger.info("\n📊 Test 1: Count all customers")
            result = await provider.execute_query(
                f"SELECT COUNT(*) as total_customers FROM {SCHEMA_NAME}.customers"
            )
            logger.info(f"Result: {result}")

            logger.info("\n📊 Test 2: Count stores")
            result = await provider.execute_query(
                f"SELECT COUNT(*) as total_stores FROM {SCHEMA_NAME}.stores"
            )
            logger.info(f"Result: {result}")

            logger.info("\n📊 Test 3: Count categories and types")
            result = await provider.execute_query(
                f"SELECT COUNT(*) as total_categories FROM {SCHEMA_NAME}.categories"
            )
            logger.info(f"Result: {result}")

            logger.info("\n📊 Test 4: Orders with revenue")
            result = await provider.execute_query(
                f"""SELECT COUNT(DISTINCT o.order_id) as orders, 
                    SUM(oi.total_amount) as revenue 
                    FROM {SCHEMA_NAME}.orders o 
                    JOIN {SCHEMA_NAME}.order_items oi ON o.order_id = oi.order_id 
                    LIMIT 1"""
            )
            logger.info(f"Result: {result}")

            logger.info("\n✅ SQL Query tests completed!")
            logger.info("=" * 50)
            print(f"\n📋 All table schemas in {SCHEMA_NAME} schema:\n")

            # --- Use print for clean, user-facing schema info ---
            print(await provider.get_table_metadata_string(STORES_TABLE))
            print(await provider.get_table_metadata_string(CATEGORIES_TABLE))
            print(await provider.get_table_metadata_string(PRODUCT_TYPES_TABLE))
            print(await provider.get_table_metadata_string(PRODUCTS_TABLE))
            print(await provider.get_table_metadata_string(CUSTOMERS_TABLE))
            print(await provider.get_table_metadata_string(ORDERS_TABLE))
            print(await provider.get_table_metadata_string(ORDER_ITEMS_TABLE))
            print(await provider.get_table_metadata_string(INVENTORY_TABLE))

    except Exception as e:
        logger.error(f"❌ Error during analysis: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
