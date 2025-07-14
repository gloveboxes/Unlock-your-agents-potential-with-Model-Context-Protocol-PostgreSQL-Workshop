#!/usr/bin/env python3
"""
Provides comprehensive customer sales database access with individual table schema tools for Zava Retail DIY Business.
"""

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field
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


async def get_table_schema(table_name: str, manager_id:str) -> str:
    """Returns the complete schema information for a table."""

    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string(table_name, manager_id=manager_id)
        return f"\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving {table_name} table schema: {e!s}"


@mcp.tool()
async def get_multiple_table_schemas(
    table_names: Annotated[
        list[str],
        Field(
            description="List of table names. Valid table names include 'retail.customers', 'retail.stores', 'retail.categories', 'retail.product_types', 'retail.products', 'retail.orders', 'retail.order_items', 'retail.inventory'."
        ),
    ],
    manager_id: Annotated[str, Field(description="PostgreSQL Manager ID required for Record Level Security (RLS).")],
) -> str:
    """
    Retrieve schemas for multiple tables in one call. Use this tool only for schemas you have not already fetched during the conversation.

    Args:
        table_names: List of table names. Valid table names include 'retail.customers', 'retail.stores', 'retail.categories', 'retail.product_types', 'retail.products', 'retail.orders', 'retail.order_items', 'retail.inventory'.

    Returns:
        Concatenated schema strings for the requested tables.
    """
    if not table_names:
        return "Error: table_names parameter is required and cannot be empty"

    valid_tables = {
        "retail.customers",
        "retail.stores",
        "retail.categories",
        "retail.product_types",
        "retail.products",
        "retail.orders",
        "retail.order_items",
        "retail.inventory",
    }

    # Validate table names
    invalid_tables = [name for name in table_names if name not in valid_tables]
    if invalid_tables:
        return f"Error: Invalid table names: {invalid_tables}. Valid tables are: {sorted(valid_tables)}"

    print(f"Manager ID: {manager_id}")
    print(f"Retrieving schemas for tables: {', '.join(table_names)}")

    schemas = []
    for table_name in table_names:
        try:
            schema_info = await get_table_schema(table_name, manager_id=manager_id)
            schemas.append(schema_info)
        except Exception as e:
            schemas.append(f"Error retrieving {table_name} schema: {e!s}")

    return "".join(schemas)


@mcp.tool()
async def execute_sales_query(
    postgresql_query: Annotated[str, Field(description="A well-formed PostgreSQL query.")],
    manager_id: Annotated[str, Field(description="PostgreSQL Manager ID required for Record Level Security (RLS).")],
) -> str:
    """Run a PostgreSQL query against the sales database by first using get_multiple_table_schemas() to retrieve schemas for any tables you haven't yet obtained, then, if your query depends on the current date or time, call get_current_utc_date() to get the current UTC date/time. Always compose your SQL using the exact table and column names from these schemas, and pass the query to this tool for execution. For more readable results, join related tables to show descriptive fields such as customer names, product names, store names, and category names; distinguish online and physical stores using the is_online flag (for example, CASE WHEN s.is_online THEN 'Online' ELSE 'Physical' END AS store_type); and, unless the user specifically asks for raw data, prefer aggregated results using functions like SUM, AVG, COUNT, and GROUP BY. ALWAYS Limit the number of rows returned to 20 or fewer to avoid overwhelming the user with too much data and explain that results are limited for performance and readability.

    Args:
        postgresql_query: A well-formed PostgreSQL query.

    Returns:
        Query results as a string.
    """
    print(f"Manager ID: {manager_id}")
    print(f"Executing PostgreSQL query: {postgresql_query}")
    try:
        if not postgresql_query:
            return "Error: postgresql_query parameter is required"

        provider = get_db_provider()
        result = await provider.execute_query(postgresql_query, manager_id=manager_id)
        return f"Query Results:\n{result}"

    except Exception as e:
        return f"Error executing database query: {e!s}"


@mcp.tool()
async def get_current_utc_date() -> str:
    """Get the current UTC date and time in ISO format. Useful for date-based queries,
    filtering recent data, or understanding the current context for time-sensitive analysis.

    Returns:
        Current UTC date and time in ISO format (YYYY-MM-DDTHH:MM:SS.fffffZ)
    """
    print("Retrieving current UTC date and time")
    try:
        current_utc = datetime.now(timezone.utc)
        return f"Current UTC Date/Time: {current_utc.isoformat()}"
    except Exception as e:
        return f"Error retrieving current UTC date: {e!s}"


async def run_http_server() -> None:
    """Run the MCP server in HTTP mode."""
    # Configure server settings
    mcp.settings.port = 8010
    # mcp.settings.stateless_http = True

    print(
        f"📡 MCP endpoint available at: http://{mcp.settings.host}:{mcp.settings.port}/mcp")

    # Run the FastMCP server as HTTP endpoint
    await mcp.run_streamable_http_async()


def main() -> None:
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true",
                        help="Run server in stdio mode")
    args = parser.parse_args()

    if args.stdio:
        mcp.run()
    else:
        # Run the HTTP server
        asyncio.run(run_http_server())


if __name__ == "__main__":
    main()
