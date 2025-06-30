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
    await db.open_connection()

    try:
        yield AppContext(db=db)
    finally:
        # Cleanup on shutdown
        try:
            await db.close_connection()
        except Exception as e:
            print(f"⚠️  Error closing database: {e}")


# Create MCP server with lifespan support
mcp = FastMCP("customer-sales-tools", lifespan=app_lifespan)


def get_db_provider() -> PostgreSQLSchemaProvider:
    """Get the database provider instance from context."""
    ctx = mcp.get_context()
    app_context = ctx.request_context.lifespan_context
    if isinstance(app_context, AppContext):
        return app_context.db
    raise RuntimeError("Invalid lifespan context type")


@mcp.tool()
async def get_customers_table_schema() -> str:
    """Get the complete schema information for the customers table. **ALWAYS call this tool first** when queries involve customer data, customer information, or customer-related analysis. This provides table structure and column types.

    Note: Customers are independent entities with no direct store relationship - store information is tracked per order in the orders table. **CRITICAL**: ALWAYS include customer first_name and last_name in results - never return just customer_id as it is not human-readable.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("customers")
        return f"Customers Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving customers table schema: {e!s}"


@mcp.tool()
async def get_products_table_schema() -> str:
    """Get the complete schema information for the products table. **ALWAYS call this tool first** when queries involve product data, product analysis, or product-related queries. This provides table structure with normalized category and type references.

    Note: Products contain a unique SKU field for business identification and reference category_id and type_id instead of storing text directly. **CRITICAL**: ALWAYS join with categories and product_types tables to return category_name and type_name - never return just IDs as they are not human-readable.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("products")
        return f"Products Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving products table schema: {e!s}"


@mcp.tool()
async def get_orders_table_schema() -> str:
    """Get the complete schema information for the orders table. **ALWAYS call this tool first** when queries involve order headers, order dates, customer orders, or store-based analysis. This provides order header information only.

    Note: This table contains order headers (order_id, customer_id, store_id, order_date). **CRITICAL**: ALWAYS join with customers table for customer names and stores table for store names - never return just customer_id or store_id as they are not human-readable. For product details and pricing, join with order_items table.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("orders")
        return f"Orders Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving orders table schema: {e!s}"


@mcp.tool()
async def get_inventory_table_schema() -> str:
    """Get the complete schema information for the inventory table. **ALWAYS call this tool first** when queries involve inventory data, stock levels, or inventory-related analysis. This provides table structure showing stock levels for each product at each store location, column types, and relationships.

    Note: Inventory is tracked per store_id and product_id combination, allowing different stock levels at each store location. **CRITICAL**: ALWAYS join with stores table for store_name and products table (then categories/product_types) for product_name, category_name, type_name - never return just store_id or product_id as they are not human-readable.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("inventory")
        return f"Inventory Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving inventory table schema: {e!s}"


@mcp.tool()
async def get_stores_table_schema() -> str:
    """Get the complete schema information for the stores table. **ALWAYS call this tool first** when queries involve store locations, store names, or store-related analysis. This provides table structure with store_id and store_name only - a clean reference table for store information.

    Note: This table contains only core store information (store_id, store_name). Store performance data comes from joining with orders table.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("stores")
        return f"Stores Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving stores table schema: {e!s}"


@mcp.tool()
async def get_categories_table_schema() -> str:
    """Get the complete schema information for the categories table. **ALWAYS call this tool first** when queries involve product categories, category analysis, or category-related data. This provides the master category lookup table.

    Note: This is a lookup table containing category_id and category_name. Products reference this table via category_id.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("categories")
        return f"Categories Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving categories table schema: {e!s}"


@mcp.tool()
async def get_product_types_table_schema() -> str:
    """Get the complete schema information for the product_types table. **ALWAYS call this tool first** when queries involve product types, subcategories, or product type analysis. This provides the product type lookup table linked to categories.

    Note: This table contains type_id, category_id, and type_name. It links product types to their parent categories."""
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("product_types")
        return f"Product Types Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving product_types table schema: {e!s}"


@mcp.tool()
async def get_order_items_table_schema() -> str:
    """Get the complete schema information for the order_items table. **ALWAYS call this tool first** when queries involve line item details, product quantities, pricing, discounts, or sales revenue analysis. This provides detailed information about products within orders.

    Note: This table contains the actual sales transactions with product_id, quantities, pricing, and totals. Each row represents one product within an order. **CRITICAL**: ALWAYS join with products table and then with categories/product_types tables to return product_name, category_name, and type_name - never return just product_id as it is not human-readable.
    """
    try:
        provider = get_db_provider()
        schema_info = await provider.get_table_metadata_string("order_items")
        return f"Order Items Table Schema:\n\n{schema_info}"
    except Exception as e:
        return f"Error retrieving order_items table schema: {e!s}"


@mcp.tool()
async def execute_sales_query(postgresql_query: str) -> str:
    """Execute a PostgreSQL query against the customer sales database.

    CRITICAL WORKFLOW - ALWAYS FOLLOW THIS ORDER:
    1. **FIRST**: Call the appropriate schema tool(s) based on your query needs:
       - get_customers_table_schema: For customer data (customer_id, names, email, phone)
       - get_stores_table_schema: For store names and IDs (store_id, store_name)
       - get_categories_table_schema: For product category lookup (category_id, category_name)
       - get_product_types_table_schema: For product type lookup (type_id, category_id, type_name)
       - get_products_table_schema: For product data (references category_id and type_id)
       - get_orders_table_schema: For order headers (order_id, customer_id, store_id, order_date)
       - get_order_items_table_schema: For line items with pricing (order_item_id, quantities, prices)
       - get_inventory_table_schema: For stock levels per store and product
    2. **THEN**: Write your query using the exact table/column names from the schema
    3. **FINALLY**: Execute the query with this tool

    QUERY GUIDELINES:
    - **ALWAYS RETURN HUMAN-READABLE NAMES**: Never return just IDs - always include names alongside IDs
    - **MANDATORY JOINS FOR READABILITY**:
      * Products: ALWAYS join with categories and product_types to get category_name, type_name
      * Customers: ALWAYS include customer first_name, last_name (not just customer_id)
      * Stores: ALWAYS include store_name (not just store_id)
      * Orders: ALWAYS join with customers and stores for names
    - Default to aggregation (SUM, AVG, COUNT, GROUP BY) unless user requests details
    - Always include LIMIT 20 in every query - never return more than 20 rows
    - Use only valid table and column names from the schema
    - Never return all rows from any table without aggregation

    MANDATORY JOIN PATTERNS FOR READABLE RESULTS:
    - Orders + Customer Names: orders o JOIN customers c ON o.customer_id = c.customer_id
    - Orders + Store Names: orders o JOIN stores s ON o.store_id = s.store_id
    - Products + Full Names: products p JOIN categories cat ON p.category_id = cat.category_id JOIN product_types pt ON p.type_id = pt.type_id
    - Order Items + Product Names: order_items oi JOIN products p ON oi.product_id = p.product_id JOIN categories cat ON p.category_id = cat.category_id JOIN product_types pt ON p.type_id = pt.type_id
    - Complete Order View: orders o JOIN customers c ON o.customer_id = c.customer_id JOIN stores s ON o.store_id = s.store_id JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id JOIN categories cat ON p.category_id = cat.category_id JOIN product_types pt ON p.type_id = pt.type_id

    EXAMPLE GOOD QUERIES:
    - Product Sales: SELECT cat.category_name, pt.type_name, p.product_name, p.sku, SUM(oi.total_price) as revenue FROM products p JOIN categories cat ON p.category_id = cat.category_id JOIN product_types pt ON p.type_id = pt.type_id JOIN order_items oi ON p.product_id = oi.product_id GROUP BY cat.category_name, pt.type_name, p.product_name, p.sku ORDER BY revenue DESC LIMIT 20
    - Customer Orders: SELECT c.first_name, c.last_name, s.store_name, o.order_date, COUNT(*) as order_count FROM orders o JOIN customers c ON o.customer_id = c.customer_id JOIN stores s ON o.store_id = s.store_id GROUP BY c.first_name, c.last_name, s.store_name, o.order_date LIMIT 20

    Args:
        postgresql_query: A well-formed PostgreSQL query to extract sales data. Must include LIMIT 20.
    """
    try:
        if not postgresql_query:
            return "Error: postgresql_query parameter is required"

        # Validate that query includes LIMIT
        if "LIMIT" not in postgresql_query.upper():
            return "Error: Query must include 'LIMIT 20' to prevent returning too many rows. Please modify your query."

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
    # Run the FastMCP server
    mcp.run()
