#!/usr/bin/env python3
"""
Provides comprehensive customer sales database access with individual table schema tools for Zava Retail DIY Business.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from sales_data_postgres import PostgreSQLSchemaProvider


@dataclass
class AppContext:
    """Application context containing database connection."""

    db: PostgreSQLSchemaProvider


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context"""

    db = PostgreSQLSchemaProvider()
    # Use connection pool instead of single connection for HTTP server
    await db.create_pool()

    try:
        yield AppContext(db=db)
    finally:
        # Cleanup on shutdown
        try:
            await db.close_pool()
        except Exception as e:
            print(f"⚠️  Error closing database pool: {e}")


# Create MCP server with lifespan support
mcp = FastMCP("mcp-zava-sales-devcontainer",
              lifespan=app_lifespan, stateless_http=True)


def get_db_provider() -> PostgreSQLSchemaProvider:
    """Get the database provider instance from context."""
    ctx = mcp.get_context()
    app_context = ctx.request_context.lifespan_context
    if isinstance(app_context, AppContext):
        return app_context.db
    raise RuntimeError("Invalid lifespan context type")


async def get_table_schema(table_name: str) -> str:
    """Returns the complete schema information for a table."""

    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string(table_name)
        return f"\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving {table_name} table schema: {e!s}"


@mcp.tool()
async def get_multiple_table_schemas(table_names: list[str]) -> str:
    """Retrieve schemas for multiple tables in one call.

    Use this tool only for schemas you have not already fetched during the conversation; supply a list of valid table names.
    
    Valid table names include:
    - retail.customers
    - retail.stores
    - retail.categories
    - retail.product_types
    - retail.products
    - retail.orders
    - retail.order_items
    - retail.inventory

    Args:
        table_names: List of table names (e.g., ["retail.customers", "retail.stores"]).

    Returns:
        Concatenated schema strings for the requested tables.
    """
    if not table_names:
        return "Error: table_names parameter is required and cannot be empty"

    valid_tables = {
        "retail.customers", "retail.stores", "retail.categories", "retail.product_types",
        "retail.products", "retail.orders", "retail.order_items", "retail.inventory"
    }

    # Validate table names
    invalid_tables = [name for name in table_names if name not in valid_tables]
    if invalid_tables:
        return f"Error: Invalid table names: {invalid_tables}. Valid tables are: {sorted(valid_tables)}"

    print(f"Retrieving schemas for tables: {', '.join(table_names)}")

    schemas = []
    for table_name in table_names:
        try:
            schema_info = await get_table_schema(table_name)
            schemas.append(schema_info)
        except Exception as e:
            schemas.append(f"Error retrieving {table_name} schema: {e!s}")

    return "".join(schemas)


@mcp.tool()
async def execute_sales_query(postgresql_query: str) -> str:
    """Run a PostgreSQL query against the sales database.

    Workflow:
    1. **ALWAYS** first call get_multiple_table_schemas() for any tables whose schemas you have not yet obtained.
    2. Compose your SQL using the exact table and column names from those schemas.
    3. Pass the SQL to this tool to execute it.

    Guidelines for readable output:
    - Join related tables to include descriptive fields (customer names, product names, store names, category names, etc.).
    - Distinguish online vs physical stores using the is_online flag (`CASE WHEN s.is_online THEN 'Online' ELSE 'Physical' END AS store_type`).
    - Prefer aggregated results (SUM, AVG, COUNT, GROUP BY) unless the user explicitly requests raw rows.

    Args:
        postgresql_query: A well‑formed PostgreSQL query.

    Returns:
        Query results as a string.
    """
    print(f"Executing PostgreSQL query: {postgresql_query}")
    try:
        if not postgresql_query:
            return "Error: postgresql_query parameter is required"

        provider = get_db_provider()
        result = await provider.execute_query(postgresql_query)
        return f"Query Results:\n{result}"

    except Exception as e:
        return f"Error executing database query: {e!s}"


@mcp.tool()
async def get_current_utc_date() -> str:
    """Get the current UTC date and time in ISO format.

    Returns the current date and time in UTC timezone, useful for date-based queries,
    filtering recent data, or understanding the current context for time-sensitive analysis.

    Returns:
        Current UTC date and time in ISO format (YYYY-MM-DDTHH:MM:SS.fffffZ)
    """
    try:
        current_utc = datetime.now(timezone.utc)
        return f"Current UTC Date/Time: {current_utc.isoformat()}"
    except Exception as e:
        return f"Error retrieving current UTC date: {e!s}"


if __name__ == "__main__":
    import asyncio

    # For HTTP server mode, run using asyncio
    async def main() -> None:
        # Configure server settings
        mcp.settings.port = 8010
        # mcp.settings.stateless_http = True

        print(
            f"📡 MCP endpoint available at: http://{mcp.settings.host}:{mcp.settings.port}/mcp")

        # Run the FastMCP server as HTTP endpoint
        await mcp.run_streamable_http_async()

    # Run the HTTP server
    asyncio.run(main())
