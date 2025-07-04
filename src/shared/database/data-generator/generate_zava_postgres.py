"""
Customer Sales Database Generator for PostgreSQL with pgvector

This script generates a comprehensive customer sales database with optimized indexing
and vector embeddings support for PostgreSQL with pgvector extension.

DATA FILE STRUCTURE:
- product_data.json: Contains all product information (main_categories with products)
- reference_data.json: Contains store configurations (weights, year weights)

POSTGRESQL CONNECTION:
- Requires PostgreSQL with pgvector extension enabled
- Uses async connections via asyncpg
- Targets retail schema in zava database

FEATURES:
- Complete database generation with customers, products, stores, orders
- Product embeddings population from product_data.json
- Vector similarity indexing with pgvector
- Performance-optimized indexes
- Comprehensive statistics and verification

USAGE:
    python generate_zava_postgres.py                     # Generate complete database
    python generate_zava_postgres.py --show-stats        # Show database statistics
    python generate_zava_postgres.py --embeddings-only   # Populate embeddings only
    python generate_zava_postgres.py --verify-embeddings # Verify embeddings table
    python generate_zava_postgres.py --help              # Show all options
"""

import asyncio
import json
import logging
import os
import random
from datetime import date
from typing import Dict, List, Optional, Tuple

import asyncpg
from dotenv import load_dotenv
from faker import Faker

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
# Try to load .env from script directory first, then parent directories
env_paths = [
    os.path.join(script_dir, '.env'),
    os.path.join(script_dir, '..', '..', '..', '.env'),  # Up to workspace root
]

for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
else:
    # Fallback to default behavior
    load_dotenv()

# Initialize Faker and logging
fake = Faker()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# PostgreSQL connection configuration
POSTGRES_CONFIG = {
    'host': os.getenv('postgres_host', 'db'),
    'port': int(os.getenv('postgres_port', '5432')),
    'user': os.getenv('postgres_user', 'postgres'),
    'password': os.getenv('postgres_password', 'P@ssw0rd!'),
    'database': os.getenv('postgres_db', 'zava')
}

SCHEMA_NAME = 'retail'

# Load reference data from JSON file
def load_reference_data():
    """Load reference data from JSON file"""
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'reference_data.json')
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load reference data: {e}")
        raise

def load_product_data():
    """Load product data from JSON file"""
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'product_data.json')
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load product data: {e}")
        raise

# Load the reference data
reference_data = load_reference_data()
product_data = load_product_data()

# Get reference data from loaded JSON
main_categories = product_data['main_categories']
stores = reference_data['stores']

# Check if seasonal trends are available
seasonal_categories = []
for category_name, category_data in main_categories.items():
    if 'washington_seasonal_multipliers' in category_data:
        seasonal_categories.append(category_name)

if seasonal_categories:
    logging.info(f"🗓️  Washington State seasonal trends active for {len(seasonal_categories)} categories: {', '.join(seasonal_categories)}")
else:
    logging.info("⚠️  No seasonal trends found - using equal weights for all categories")

def weighted_store_choice():
    """Choose a store based on weighted distribution"""
    store_names = list(stores.keys())
    weights = [stores[store]['customer_distribution_weight'] for store in store_names]
    return random.choices(store_names, weights=weights, k=1)[0]

def generate_phone_number(region=None):
    """Generate a phone number in North American format (XXX) XXX-XXXX"""
    return f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

async def create_connection():
    """Create async PostgreSQL connection"""
    try:
        conn = await asyncpg.connect(**POSTGRES_CONFIG)
        logging.info(f"Connected to PostgreSQL at {POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}")
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to PostgreSQL: {e}")
        raise

async def create_database_schema(conn):
    """Create database schema, tables and indexes"""
    try:
        # Create schema if it doesn't exist
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
        logging.info(f"Schema '{SCHEMA_NAME}' created or already exists")
        
        # Enable pgvector extension if available
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            logging.info("pgvector extension enabled")
        except Exception as e:
            logging.warning(f"pgvector extension not available: {e}")
        
        # Create stores table
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.stores (
                store_id SERIAL PRIMARY KEY,
                store_name TEXT UNIQUE NOT NULL
            )
        """)
        
        # Create customers table
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.customers (
                customer_id SERIAL PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT
            )
        """)
        
        # Create categories table
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.categories (
                category_id SERIAL PRIMARY KEY,
                category_name TEXT NOT NULL UNIQUE
            )
        """)
        
        # Create product_types table
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.product_types (
                type_id SERIAL PRIMARY KEY,
                category_id INTEGER NOT NULL,
                type_name TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES {SCHEMA_NAME}.categories (category_id)
            )
        """)
        
        # Create products table with optional vector embedding column
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.products (
                product_id SERIAL PRIMARY KEY,
                sku TEXT UNIQUE NOT NULL,
                product_name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                type_id INTEGER NOT NULL,
                base_price DECIMAL(10,2) NOT NULL,
                product_description TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES {SCHEMA_NAME}.categories (category_id),
                FOREIGN KEY (type_id) REFERENCES {SCHEMA_NAME}.product_types (type_id)
            )
        """)
        
        # Create inventory table
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.inventory (
                store_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stock_level INTEGER NOT NULL,
                PRIMARY KEY (store_id, product_id),
                FOREIGN KEY (store_id) REFERENCES {SCHEMA_NAME}.stores (store_id),
                FOREIGN KEY (product_id) REFERENCES {SCHEMA_NAME}.products (product_id)
            )
        """)
        
        # Create orders table (header only)
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.orders (
                order_id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                store_id INTEGER NOT NULL,
                order_date DATE NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES {SCHEMA_NAME}.customers (customer_id),
                FOREIGN KEY (store_id) REFERENCES {SCHEMA_NAME}.stores (store_id)
            )
        """)
        
        # Create order_items table (line items)
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.order_items (
                order_item_id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                discount_percent INTEGER DEFAULT 0,
                discount_amount DECIMAL(10,2) DEFAULT 0,
                total_amount DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES {SCHEMA_NAME}.orders (order_id),
                FOREIGN KEY (product_id) REFERENCES {SCHEMA_NAME}.products (product_id)
            )
        """)
        
        # Create product_embeddings table for image data
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.product_embeddings (
                embedding_id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                image_url TEXT NOT NULL,
                image_embedding vector(512),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES {SCHEMA_NAME}.products (product_id)
            )
        """)
        
        # Create optimized performance indexes
        logging.info("Creating performance indexes...")
        
        # Category and type indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_categories_name ON {SCHEMA_NAME}.categories(category_name)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_product_types_category ON {SCHEMA_NAME}.product_types(category_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_product_types_name ON {SCHEMA_NAME}.product_types(type_name)")
        
        # Product indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_sku ON {SCHEMA_NAME}.products(sku)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_category ON {SCHEMA_NAME}.products(category_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_type ON {SCHEMA_NAME}.products(type_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_price ON {SCHEMA_NAME}.products(base_price)")
        
        # Vector similarity index (if pgvector is available)
        try:
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_embedding ON {SCHEMA_NAME}.products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
            logging.info("Vector similarity index created")
        except Exception as e:
            logging.warning(f"Could not create vector index: {e}")
        
        # Inventory indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_inventory_store_product ON {SCHEMA_NAME}.inventory(store_id, product_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_inventory_product ON {SCHEMA_NAME}.inventory(product_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_inventory_store ON {SCHEMA_NAME}.inventory(store_id)")
        
        # Store indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_stores_name ON {SCHEMA_NAME}.stores(store_name)")
        
        # Order indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_orders_customer ON {SCHEMA_NAME}.orders(customer_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_orders_store ON {SCHEMA_NAME}.orders(store_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_orders_date ON {SCHEMA_NAME}.orders(order_date)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_orders_customer_date ON {SCHEMA_NAME}.orders(customer_id, order_date)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_orders_store_date ON {SCHEMA_NAME}.orders(store_id, order_date)")
        
        # Order items indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_order_items_order ON {SCHEMA_NAME}.order_items(order_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_order_items_product ON {SCHEMA_NAME}.order_items(product_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_order_items_total ON {SCHEMA_NAME}.order_items(total_amount)")
        
        # Product embeddings indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_product_embeddings_product ON {SCHEMA_NAME}.product_embeddings(product_id)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_product_embeddings_url ON {SCHEMA_NAME}.product_embeddings(image_url)")
        
        # Vector similarity index for product embeddings (if pgvector is available)
        try:
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_product_embeddings_vector ON {SCHEMA_NAME}.product_embeddings USING ivfflat (image_embedding vector_cosine_ops) WITH (lists = 100)")
            logging.info("Product embeddings vector similarity index created")
        except Exception as e:
            logging.warning(f"Could not create product embeddings vector index: {e}")
        
        # Covering indexes for aggregation queries
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_order_items_covering ON {SCHEMA_NAME}.order_items(order_id, product_id, total_amount, quantity)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_covering ON {SCHEMA_NAME}.products(category_id, type_id, product_id, sku, base_price)")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_products_sku_covering ON {SCHEMA_NAME}.products(sku, product_id, product_name, base_price)")
        
        # Customer indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_customers_email ON {SCHEMA_NAME}.customers(email)")
        
        logging.info("Performance indexes created successfully!")
        logging.info("Database schema created successfully!")
    except Exception as e:
        logging.error(f"Error creating database schema: {e}")
        raise

async def batch_insert(conn, query: str, data: List[Tuple], batch_size: int = 1000):
    """Insert data in batches using asyncio"""
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        await conn.executemany(query, batch)

async def insert_customers(conn, num_customers: int = 100000):
    """Insert customer data into the database"""
    try:
        logging.info(f"Generating {num_customers:,} customers...")
        
        customers_data = []
        
        for i in range(1, num_customers + 1):
            first_name = fake.first_name().replace("'", "''")  # Escape single quotes
            last_name = fake.last_name().replace("'", "''")
            email = f"{first_name.lower()}.{last_name.lower()}.{i}@example.com"
            phone = generate_phone_number()
            
            customers_data.append((first_name, last_name, email, phone))
        
        await batch_insert(conn, f"INSERT INTO {SCHEMA_NAME}.customers (first_name, last_name, email, phone) VALUES ($1, $2, $3, $4)", customers_data)
        
        logging.info(f"Successfully inserted {num_customers:,} customers!")
    except Exception as e:
        logging.error(f"Error inserting customers: {e}")
        raise

async def insert_stores(conn):
    """Insert store data into the database"""
    try:
        logging.info("Generating stores...")
        
        stores_data = []
        
        for store_name, store_config in stores.items():
            stores_data.append((store_name,))
        
        await batch_insert(conn, f"INSERT INTO {SCHEMA_NAME}.stores (store_name) VALUES ($1)", stores_data)
        
        logging.info(f"Successfully inserted {len(stores_data):,} stores!")
    except Exception as e:
        logging.error(f"Error inserting stores: {e}")
        raise

async def insert_categories(conn):
    """Insert category data into the database"""
    try:
        logging.info("Generating categories...")
        
        categories_data = []
        
        # Extract unique categories from product data
        for main_category in main_categories.keys():
            categories_data.append((main_category,))
        
        await batch_insert(conn, f"INSERT INTO {SCHEMA_NAME}.categories (category_name) VALUES ($1)", categories_data)
        
        logging.info(f"Successfully inserted {len(categories_data):,} categories!")
    except Exception as e:
        logging.error(f"Error inserting categories: {e}")
        raise

async def insert_product_types(conn):
    """Insert product type data into the database"""
    try:
        logging.info("Generating product types...")
        
        product_types_data = []
        
        # Get category_id mapping
        category_mapping = {}
        rows = await conn.fetch(f"SELECT category_id, category_name FROM {SCHEMA_NAME}.categories")
        for row in rows:
            category_mapping[row['category_name']] = row['category_id']
        
        # Extract product types for each category
        for main_category, subcategories in main_categories.items():
            category_id = category_mapping[main_category]
            for subcategory in subcategories.keys():
                # Skip the seasonal multipliers key
                if subcategory == 'washington_seasonal_multipliers':
                    continue
                
                product_types_data.append((category_id, subcategory))
        
        await batch_insert(conn, f"INSERT INTO {SCHEMA_NAME}.product_types (category_id, type_name) VALUES ($1, $2)", product_types_data)
        
        logging.info(f"Successfully inserted {len(product_types_data):,} product types!")
    except Exception as e:
        logging.error(f"Error inserting product types: {e}")
        raise

async def insert_products(conn):
    """Insert product data into the database"""
    try:
        logging.info("Generating products...")
        
        # Get category and type mappings
        category_mapping = {}
        rows = await conn.fetch(f"SELECT category_id, category_name FROM {SCHEMA_NAME}.categories")
        for row in rows:
            category_mapping[row['category_name']] = row['category_id']
        
        type_mapping = {}
        rows = await conn.fetch(f"SELECT type_id, type_name, category_id FROM {SCHEMA_NAME}.product_types")
        for row in rows:
            type_mapping[(row['category_id'], row['type_name'])] = row['type_id']
        
        products_data = []
        
        for main_category, subcategories in main_categories.items():
            category_id = category_mapping[main_category]
            
            for subcategory, product_list in subcategories.items():
                # Skip the seasonal multipliers key, only process actual product types
                if subcategory == 'washington_seasonal_multipliers':
                    continue
                    
                if not product_list:  # Handle empty product lists
                    continue
                
                type_id = type_mapping.get((category_id, subcategory))
                if not type_id:
                    logging.warning(f"Type ID not found for category {main_category}, type {subcategory}")
                    continue
                    
                for product_details in product_list:
                    product_name = product_details["name"]
                    sku = product_details.get("sku", f"SKU{len(products_data)+1:06d}")  # Fallback if no SKU
                    fixed_price = product_details["price"]
                    description = product_details["description"]
                    base_price = float(fixed_price)
                    products_data.append((sku, product_name, category_id, type_id, base_price, description))
        
        await batch_insert(conn, f"INSERT INTO {SCHEMA_NAME}.products (sku, product_name, category_id, type_id, base_price, product_description) VALUES ($1, $2, $3, $4, $5, $6)", products_data)
        
        logging.info(f"Successfully inserted {len(products_data):,} products!")
        return len(products_data)  # Return the number of products inserted
    except Exception as e:
        logging.error(f"Error inserting products: {e}")
        raise

def get_store_multipliers(store_name):
    """Get order frequency multipliers based on store name"""
    store_data = stores.get(store_name, {
        'customer_distribution_weight': 1,
        'order_frequency_multiplier': 1.0, 
        'order_value_multiplier': 1.0
    })
    return {'orders': store_data.get('order_frequency_multiplier', 1.0)}

def get_yearly_weight(year):
    """Get the weight for each year to create growth pattern"""
    return reference_data['year_weights'].get(str(year), 1.0)

def weighted_year_choice():
    """Choose a year based on growth pattern weights"""
    years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    weights = [get_yearly_weight(year) for year in years]
    return random.choices(years, weights=weights, k=1)[0]

async def get_store_id_by_name(conn, store_name):
    """Get store_id for a given store name"""
    row = await conn.fetchrow(f"SELECT store_id FROM {SCHEMA_NAME}.stores WHERE store_name = $1", store_name)
    return row['store_id'] if row else 1  # Default to store_id 1 if not found

def choose_seasonal_product_category(month):
    """Choose a category based on Washington State seasonal multipliers"""
    categories = []
    weights = []
    
    for category_name, category_data in main_categories.items():
        # Skip if no seasonal multipliers defined for this category
        if 'washington_seasonal_multipliers' not in category_data:
            categories.append(category_name)
            weights.append(1.0)  # Default weight
        else:
            seasonal_multipliers = category_data['washington_seasonal_multipliers']
            # Use month index (0-11) to get the multiplier
            seasonal_weight = seasonal_multipliers[month - 1]  # month is 1-12, array is 0-11
            categories.append(category_name)
            weights.append(seasonal_weight)
    
    return random.choices(categories, weights=weights, k=1)[0]

def choose_product_type(main_category):
    """Choose a product type within a category with equal weights"""
    product_types = []
    for key in main_categories[main_category].keys():
        if isinstance(main_categories[main_category][key], list):
            product_types.append(key)
    
    if not product_types:
        logging.warning(f"No product types found for category: {main_category}")
        return None
    return random.choice(product_types)

def extract_products_with_embeddings(product_data: Dict) -> List[Tuple[str, str, List[float]]]:
    """
    Extract products with image embeddings from the JSON structure.
    
    Returns:
        List of tuples: (sku, image_path, image_embedding)
    """
    products_with_embeddings = []
    
    for category_name, category_data in product_data.get('main_categories', {}).items():
        for product_type, products in category_data.items():
            # Skip non-product keys like seasonal multipliers
            if not isinstance(products, list):
                continue
                
            for product in products:
                if isinstance(product, dict):
                    sku = product.get('sku')
                    image_path = product.get('image_path')
                    image_embedding = product.get('image_embedding')
                    
                    if sku and image_path and image_embedding:
                        products_with_embeddings.append((sku, image_path, image_embedding))
                    else:
                        logging.debug(f"Skipping product with missing data: SKU={sku}")
    
    logging.info(f"Found {len(products_with_embeddings)} products with embeddings")
    return products_with_embeddings

async def get_product_id_by_sku(conn: asyncpg.Connection, sku: str) -> Optional[int]:
    """Get product_id for a given SKU"""
    try:
        result = await conn.fetchval(
            f"SELECT product_id FROM {SCHEMA_NAME}.products WHERE sku = $1",
            sku
        )
        return result
    except Exception as e:
        logging.error(f"Error getting product_id for SKU {sku}: {e}")
        return None

async def insert_product_embedding(
    conn: asyncpg.Connection, 
    product_id: int, 
    image_path: str, 
    image_embedding: List[float]
) -> bool:
    """Insert a product embedding record"""
    try:
        # Convert image_path to a proper URL (you may want to customize this)
        image_url = f"/static/images/{os.path.basename(image_path)}"
        
        # Convert the embedding list to a vector string format
        embedding_str = f"[{','.join([str(x) for x in image_embedding])}]"
        
        await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.product_embeddings 
            (product_id, image_url, image_embedding) 
            VALUES ($1, $2, $3::vector)
            """,
            product_id, image_url, embedding_str
        )
        return True
    except Exception as e:
        logging.error(f"Error inserting embedding for product_id {product_id}: {e}")
        return False

async def clear_existing_embeddings(conn: asyncpg.Connection) -> None:
    """Clear all existing product embeddings"""
    try:
        result = await conn.execute(f"DELETE FROM {SCHEMA_NAME}.product_embeddings")
        logging.info(f"Cleared existing embeddings: {result}")
    except Exception as e:
        logging.error(f"Error clearing existing embeddings: {e}")
        raise

async def populate_product_embeddings(conn: asyncpg.Connection, clear_existing: bool = False, batch_size: int = 100) -> None:
    """Populate product embeddings from product_data.json"""
    
    logging.info("Loading product data for embeddings...")
    products_with_embeddings = extract_products_with_embeddings(product_data)
    
    if not products_with_embeddings:
        logging.warning("No products with embeddings found in the data")
        return
    
    try:
        # Clear existing embeddings if requested
        if clear_existing:
            logging.info("Clearing existing product embeddings...")
            await clear_existing_embeddings(conn)
        
        # Process products in batches
        inserted_count = 0
        skipped_count = 0
        error_count = 0
        
        for i in range(0, len(products_with_embeddings), batch_size):
            batch = products_with_embeddings[i:i + batch_size]
            
            logging.info(f"Processing embeddings batch {i//batch_size + 1}/{(len(products_with_embeddings) + batch_size - 1)//batch_size}")
            
            for sku, image_path, image_embedding in batch:
                # Get product_id for this SKU
                product_id = await get_product_id_by_sku(conn, sku)
                
                if product_id is None:
                    logging.debug(f"Product not found for SKU: {sku}")
                    skipped_count += 1
                    continue
                
                # Insert the embedding
                if await insert_product_embedding(conn, product_id, image_path, image_embedding):
                    inserted_count += 1
                else:
                    error_count += 1
        
        # Summary
        logging.info("Product embeddings population complete!")
        logging.info(f"  Inserted: {inserted_count}")
        logging.info(f"  Skipped (product not found): {skipped_count}")
        logging.info(f"  Errors: {error_count}")
        logging.info(f"  Total processed: {len(products_with_embeddings)}")
        
    except Exception as e:
        logging.error(f"Error populating product embeddings: {e}")
        raise

async def verify_embeddings_table(conn: asyncpg.Connection) -> None:
    """Verify the product_embeddings table exists and show sample data"""
    try:
        # Check table existence
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = $1 AND table_name = 'product_embeddings'
            )
            """,
            SCHEMA_NAME
        )
        
        if not table_exists:
            logging.error(f"Table {SCHEMA_NAME}.product_embeddings does not exist!")
            return
        
        # Get row count
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.product_embeddings")
        if count is None:
            count = 0
        logging.info(f"Product embeddings table has {count} records")
        
        # Show sample data
        if count > 0:
            sample = await conn.fetch(
                f"""
                SELECT pe.embedding_id, pe.product_id, p.sku, p.product_name, pe.image_url,
                       vector_dims(pe.image_embedding) as embedding_dimension
                FROM {SCHEMA_NAME}.product_embeddings pe
                JOIN {SCHEMA_NAME}.products p ON pe.product_id = p.product_id
                LIMIT 5
                """
            )
            
            logging.info("Sample embeddings data:")
            for row in sample:
                logging.info(f"  ID: {row['embedding_id']}, SKU: {row['sku']}, "
                           f"Product: {row['product_name'][:50]}..., "
                           f"Embedding dim: {row['embedding_dimension']}")
        
    except Exception as e:
        logging.error(f"Error verifying embeddings table: {e}")

async def insert_inventory(conn):
    """Insert inventory data distributed across stores based on customer distribution weights and seasonal trends"""
    try:
        logging.info("Generating inventory with seasonal considerations...")
        
        # Get all stores and products with category information
        stores_data = await conn.fetch(f"SELECT store_id, store_name FROM {SCHEMA_NAME}.stores")
        products_data = await conn.fetch(f"""
            SELECT p.product_id, c.category_name 
            FROM {SCHEMA_NAME}.products p
            JOIN {SCHEMA_NAME}.categories c ON p.category_id = c.category_id
        """)
        
        # Build category to seasonal multiplier mapping (using average across year for base inventory)
        category_seasonal_avg = {}
        for category_name, category_data in main_categories.items():
            if 'washington_seasonal_multipliers' in category_data:
                seasonal_multipliers = category_data['washington_seasonal_multipliers']
                # Use average seasonal multiplier for inventory planning
                avg_multiplier = sum(seasonal_multipliers) / len(seasonal_multipliers)
                category_seasonal_avg[category_name] = avg_multiplier
            else:
                category_seasonal_avg[category_name] = 1.0  # Default multiplier
        
        inventory_data = []
        
        for store in stores_data:
            store_id = store['store_id']
            store_name = store['store_name']
            
            # Get store configuration for inventory distribution
            store_config = stores.get(store_name, {})
            base_stock_multiplier = store_config.get('customer_distribution_weight', 1.0)
            
            for product in products_data:
                product_id = product['product_id']
                category_name = product['category_name']
                
                # Get seasonal multiplier for this category
                seasonal_multiplier = category_seasonal_avg.get(category_name, 1.0)
                
                # Generate stock level based on store weight, seasonal trends, and random variation
                base_stock = random.randint(10, 100)
                stock_level = int(base_stock * base_stock_multiplier * seasonal_multiplier * random.uniform(0.5, 1.5))
                stock_level = max(1, stock_level)  # Ensure at least 1 item in stock
                
                inventory_data.append((store_id, product_id, stock_level))
        
        await batch_insert(conn, f"INSERT INTO {SCHEMA_NAME}.inventory (store_id, product_id, stock_level) VALUES ($1, $2, $3)", inventory_data)
        
        logging.info(f"Successfully inserted {len(inventory_data):,} inventory records with seasonal adjustments!")
        
    except Exception as e:
        logging.error(f"Error inserting inventory: {e}")
        raise

async def build_product_lookup(conn):
    """Build a lookup table mapping (main_category, product_type, product_name) to product_id"""
    product_lookup = {}
    
    # Get all products with their category and type information
    rows = await conn.fetch(f"""
        SELECT p.product_id, p.product_name, c.category_name, pt.type_name
        FROM {SCHEMA_NAME}.products p
        JOIN {SCHEMA_NAME}.categories c ON p.category_id = c.category_id
        JOIN {SCHEMA_NAME}.product_types pt ON p.type_id = pt.type_id
    """)
    
    for row in rows:
        key = (row['category_name'], row['type_name'], row['product_name'])
        product_lookup[key] = row['product_id']
    
    logging.info(f"Built product lookup with {len(product_lookup)} products")
    return product_lookup

async def insert_orders(conn, num_customers: int = 100000, product_lookup: Optional[Dict] = None):
    """Insert order data into the database with separate orders and order_items tables"""
    
    # Build product lookup if not provided
    if product_lookup is None:
        product_lookup = await build_product_lookup(conn)
    
    logging.info(f"Generating orders for {num_customers:,} customers...")
    
    # Get available product IDs for faster random selection and build category mapping
    product_rows = await conn.fetch(f"""
        SELECT p.product_id, p.base_price, c.category_name 
        FROM {SCHEMA_NAME}.products p
        JOIN {SCHEMA_NAME}.categories c ON p.category_id = c.category_id
    """)
    
    product_prices = {row['product_id']: float(row['base_price']) for row in product_rows}
    available_product_ids = list(product_prices.keys())
    
    # Build category to product ID mapping for seasonal selection
    category_products = {}
    for row in product_rows:
        category_name = row['category_name']
        if category_name not in category_products:
            category_products[category_name] = []
        category_products[category_name].append(row['product_id'])
    
    logging.info(f"Built category mapping with {len(category_products)} categories")
    
    total_orders = 0
    orders_data = []
    order_items_data = []
    
    for customer_id in range(1, num_customers + 1):
        # Determine store preference for this customer
        preferred_store = weighted_store_choice()
        store_id = await get_store_id_by_name(conn, preferred_store)
        
        # Get store multipliers
        store_multipliers = get_store_multipliers(preferred_store)
        order_frequency = store_multipliers['orders']
        
        # Determine number of orders for this customer (weighted by store)
        base_orders = random.choices([0, 1, 2, 3, 4, 5], weights=[20, 40, 20, 10, 7, 3], k=1)[0]
        num_orders = max(1, int(base_orders * order_frequency))
        
        for _ in range(num_orders):
            total_orders += 1
            order_id = total_orders
            
            # Generate order date with yearly growth pattern
            year = weighted_year_choice()
            month = random.randint(1, 12)
            
            # Use seasonal category selection for realistic patterns
            selected_category = None
            if seasonal_categories:
                # Choose category based on seasonal multipliers for this month
                # Increase seasonal bias by selecting seasonal category with higher probability
                if random.random() < 0.85:  # 85% seasonal selection
                    selected_category = choose_seasonal_product_category(month)
                else:
                    selected_category = random.choice(list(main_categories.keys()))
            else:
                # No seasonal trends available, use random category selection
                selected_category = random.choice(list(main_categories.keys()))
            
            # Generate random day within the month
            if month == 2:  # February
                max_day = 28 if year % 4 != 0 else 29
            elif month in [4, 6, 9, 11]:  # April, June, September, November
                max_day = 30
            else:
                max_day = 31
            
            day = random.randint(1, max_day)
            order_date = date(year, month, day)
            
            orders_data.append((customer_id, store_id, order_date))
            
            # Generate order items for this order
            num_items = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5], k=1)[0]
            
            for _ in range(num_items):
                # Select product based on seasonal category preferences
                if seasonal_categories and selected_category in category_products:
                    # Use seasonally-appropriate products with 90% probability (increased from 70%)
                    if random.random() < 0.9:
                        product_id = random.choice(category_products[selected_category])
                    else:
                        # 10% chance to select from any category (for variety)
                        product_id = random.choice(available_product_ids)
                else:
                    # No seasonal data available or category not found, use random selection
                    product_id = random.choice(available_product_ids)
                    
                base_price = product_prices[product_id]
                
                # Generate quantity and pricing
                quantity = random.choices([1, 2, 3, 4, 5], weights=[60, 25, 10, 3, 2], k=1)[0]
                unit_price = base_price * random.uniform(0.8, 1.2)  # Price variation
                
                # Apply discounts occasionally
                discount_percent = 0
                discount_amount = 0
                if random.random() < 0.15:  # 15% chance of discount
                    discount_percent = random.choice([5, 10, 15, 20, 25])
                    discount_amount = (unit_price * quantity * discount_percent) / 100
                
                total_amount = (unit_price * quantity) - discount_amount
                
                order_items_data.append((
                    order_id, product_id, quantity, unit_price, 
                    discount_percent, discount_amount, total_amount
                ))
        
        # Batch insert every 1000 customers to manage memory
        if customer_id % 1000 == 0:
            if orders_data:
                await batch_insert(conn, f"""
                    INSERT INTO {SCHEMA_NAME}.orders (customer_id, store_id, order_date) 
                    VALUES ($1, $2, $3)
                """, orders_data)
                orders_data = []
            
            if order_items_data:
                await batch_insert(conn, f"""
                    INSERT INTO {SCHEMA_NAME}.order_items 
                    (order_id, product_id, quantity, unit_price, discount_percent, discount_amount, total_amount) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, order_items_data)
                order_items_data = []
            
            if customer_id % 5000 == 0:
                logging.info(f"Processed {customer_id:,} customers, generated {total_orders:,} orders")
    
    # Insert remaining data
    if orders_data:
        await batch_insert(conn, f"""
            INSERT INTO {SCHEMA_NAME}.orders (customer_id, store_id, order_date) 
            VALUES ($1, $2, $3)
        """, orders_data)
    
    if order_items_data:
        await batch_insert(conn, f"""
            INSERT INTO {SCHEMA_NAME}.order_items 
            (order_id, product_id, quantity, unit_price, discount_percent, discount_amount, total_amount) 
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, order_items_data)
    
    logging.info(f"Successfully inserted {total_orders:,} orders!")
    
    # Get order items count
    order_items_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.order_items")
    logging.info(f"Successfully inserted {order_items_count:,} order items!")

async def verify_database_contents(conn):
    """Verify database contents and show key statistics"""
    
    logging.info("\n" + "=" * 60)
    logging.info("DATABASE VERIFICATION & STATISTICS")
    logging.info("=" * 60)
    
    # Store distribution verification
    logging.info("\n🏪 STORE SALES DISTRIBUTION:")
    rows = await conn.fetch(f"""
        SELECT s.store_name, 
               COUNT(o.order_id) as orders,
               ROUND(SUM(oi.total_amount)/1000.0, 1) || 'K' as revenue,
               ROUND(100.0 * COUNT(o.order_id) / (SELECT COUNT(*) FROM {SCHEMA_NAME}.orders), 1) || '%' as order_pct
        FROM {SCHEMA_NAME}.orders o 
        JOIN {SCHEMA_NAME}.stores s ON o.store_id = s.store_id
        JOIN {SCHEMA_NAME}.order_items oi ON o.order_id = oi.order_id
        GROUP BY s.store_id, s.store_name
        ORDER BY SUM(oi.total_amount) DESC
    """)
    
    logging.info("   Store               Orders     Revenue    % of Orders")
    logging.info("   " + "-" * 50)
    for row in rows:
        logging.info(f"   {row['store_name']:<18} {row['orders']:>6}     ${row['revenue']:>6}    {row['order_pct']:>6}")
    
    # Year-over-year growth verification
    logging.info("\n📈 YEAR-OVER-YEAR GROWTH PATTERN:")
    rows = await conn.fetch(f"""
        SELECT EXTRACT(YEAR FROM o.order_date) as year,
               COUNT(DISTINCT o.order_id) as orders,
               ROUND(SUM(oi.total_amount)/1000.0, 1) || 'K' as revenue
        FROM {SCHEMA_NAME}.orders o
        JOIN {SCHEMA_NAME}.order_items oi ON o.order_id = oi.order_id
        GROUP BY EXTRACT(YEAR FROM o.order_date)
        ORDER BY year
    """)
    
    logging.info("   Year    Orders     Revenue    Growth")
    logging.info("   " + "-" * 35)
    prev_revenue = None
    for row in rows:
        revenue_num = float(row['revenue'].replace('K', ''))
        growth = ""
        if prev_revenue is not None:
            growth_pct = ((revenue_num - prev_revenue) / prev_revenue) * 100
            growth = f"{growth_pct:+.1f}%"
        logging.info(f"   {int(row['year'])}    {row['orders']:>6}     ${row['revenue']:>6}    {growth:>6}")
        prev_revenue = revenue_num
    
    # Product category distribution
    logging.info("\n🛍️  TOP PRODUCT CATEGORIES:")
    rows = await conn.fetch(f"""
        SELECT c.category_name,
               COUNT(DISTINCT o.order_id) as orders,
               ROUND(SUM(oi.total_amount)/1000.0, 1) || 'K' as revenue
        FROM {SCHEMA_NAME}.categories c
        JOIN {SCHEMA_NAME}.products p ON c.category_id = p.category_id
        JOIN {SCHEMA_NAME}.order_items oi ON p.product_id = oi.product_id
        JOIN {SCHEMA_NAME}.orders o ON oi.order_id = o.order_id
        GROUP BY c.category_id, c.category_name
        ORDER BY SUM(oi.total_amount) DESC
        LIMIT 5
    """)
    
    logging.info("   Category             Orders     Revenue")
    logging.info("   " + "-" * 40)
    for row in rows:
        logging.info(f"   {row['category_name']:<18} {row['orders']:>6}     ${row['revenue']:>6}")
    
    # Final summary
    customers = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.customers")
    products = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.products")
    orders = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.orders")
    order_items = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.order_items")
    embeddings = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.product_embeddings")
    total_revenue = await conn.fetchval(f"SELECT SUM(total_amount) FROM {SCHEMA_NAME}.order_items")
    
    logging.info("\n✅ DATABASE SUMMARY:")
    logging.info(f"   Customers:          {customers:>8,}")
    logging.info(f"   Products:           {products:>8,}")
    logging.info(f"   Product Embeddings: {embeddings:>8,}")
    logging.info(f"   Orders:             {orders:>8,}")
    logging.info(f"   Order Items:        {order_items:>8,}")
    if total_revenue and orders:
        logging.info(f"   Total Revenue:      ${total_revenue/1000:.1f}K")
        logging.info(f"   Avg Order:          ${total_revenue/orders:.2f}")
        logging.info(f"   Orders/Customer:    {orders/customers:.1f}")
        logging.info(f"   Items/Order:        {order_items/orders:.1f}")

async def verify_seasonal_patterns(conn):
    """Verify that orders and inventory follow seasonal patterns from product_data.json"""
    
    logging.info("\n" + "=" * 60)
    logging.info("🌱 SEASONAL PATTERNS VERIFICATION")
    logging.info("=" * 60)
    
    try:
        # Test 1: Order seasonality by category and month
        logging.info("\n📊 ORDER SEASONALITY BY CATEGORY:")
        logging.info("   Testing if orders follow seasonal multipliers from product_data.json")
        
        # Get actual orders by month and category
        rows = await conn.fetch(f"""
            SELECT c.category_name,
                   EXTRACT(MONTH FROM o.order_date) as month,
                   COUNT(DISTINCT o.order_id) as order_count,
                   ROUND(AVG(oi.total_amount), 2) as avg_order_value
            FROM {SCHEMA_NAME}.orders o
            JOIN {SCHEMA_NAME}.order_items oi ON o.order_id = oi.order_id
            JOIN {SCHEMA_NAME}.products p ON oi.product_id = p.product_id
            JOIN {SCHEMA_NAME}.categories c ON p.category_id = c.category_id
            GROUP BY c.category_name, EXTRACT(MONTH FROM o.order_date)
            HAVING COUNT(DISTINCT o.order_id) > 0
            ORDER BY c.category_name, month
        """)
        
        # Organize data by category
        category_data = {}
        for row in rows:
            category = row['category_name']
            month = int(row['month'])
            if category not in category_data:
                category_data[category] = {}
            category_data[category][month] = {
                'order_count': row['order_count'],
                'avg_order_value': float(row['avg_order_value'])
            }
        
        # Compare with seasonal multipliers
        seasonal_matches = 0
        total_seasonal_categories = 0
        
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        for category_name, category_config in main_categories.items():
            if 'washington_seasonal_multipliers' not in category_config:
                continue
                
            total_seasonal_categories += 1
            seasonal_multipliers = category_config['washington_seasonal_multipliers']
            
            if category_name not in category_data:
                logging.warning(f"   ⚠️  No orders found for seasonal category: {category_name}")
                continue
            
            # Find peak and low months from data
            data_months = category_data[category_name]
            if len(data_months) < 6:  # Need reasonable sample size
                logging.warning(f"   ⚠️  Insufficient data for {category_name} ({len(data_months)} months)")
                continue
            
            # Get peak months from multipliers and data
            multiplier_peak_month = seasonal_multipliers.index(max(seasonal_multipliers)) + 1
            multiplier_low_month = seasonal_multipliers.index(min(seasonal_multipliers)) + 1
            
            data_peak_month = max(data_months.keys(), key=lambda m: data_months[m]['order_count'])
            data_low_month = min(data_months.keys(), key=lambda m: data_months[m]['order_count'])
            
            # Check if peaks align (within 3 months tolerance for seasonality to account for data variation)
            peak_match = abs(multiplier_peak_month - data_peak_month) <= 3 or \
                        abs(multiplier_peak_month - data_peak_month) >= 9  # Account for year wraparound
            
            low_match = abs(multiplier_low_month - data_low_month) <= 3 or \
                       abs(multiplier_low_month - data_low_month) >= 9
            
            # Also check if the actual seasonal trend direction is correct (high vs low months)
            data_peak_count = data_months[data_peak_month]['order_count']
            data_low_count = data_months[data_low_month]['order_count']
            
            # Verify the trend direction is correct (peak > low by reasonable margin)
            trend_correct = data_peak_count > data_low_count * 1.1  # At least 10% difference
            
            if (peak_match or low_match) and trend_correct:
                seasonal_matches += 1
                status = "✅"
            elif peak_match or low_match or trend_correct:
                seasonal_matches += 0.5  # Partial credit for trend direction
                status = "⚠️ "
            else:
                status = "❌"
            
            logging.info(f"   {status} {category_name}:")
            logging.info(f"      Expected peak: {month_names[multiplier_peak_month-1]} ({max(seasonal_multipliers):.1f})")
            logging.info(f"      Actual peak:   {month_names[data_peak_month-1]} ({data_months[data_peak_month]['order_count']} orders)")
            logging.info(f"      Expected low:  {month_names[multiplier_low_month-1]} ({min(seasonal_multipliers):.1f})")
            logging.info(f"      Actual low:    {month_names[data_low_month-1]} ({data_months[data_low_month]['order_count']} orders)")
        
        # Test 2: Inventory seasonality
        logging.info("\n📦 INVENTORY SEASONALITY:")
        logging.info("   Testing if inventory levels reflect seasonal patterns")
        
        # Initialize inventory tracking variables
        inventory_matches = 0
        total_inventory_categories = 0
        inventory_match_rate = 0
        
        # Get average inventory by category
        inventory_rows = await conn.fetch(f"""
            SELECT c.category_name,
                   AVG(i.stock_level) as avg_stock,
                   COUNT(*) as product_count
            FROM {SCHEMA_NAME}.inventory i
            JOIN {SCHEMA_NAME}.products p ON i.product_id = p.product_id
            JOIN {SCHEMA_NAME}.categories c ON p.category_id = c.category_id
            GROUP BY c.category_name
            ORDER BY avg_stock DESC
        """)
        
        # Calculate expected inventory ratios based on seasonal averages
        expected_inventory = {}
        for category_name, category_config in main_categories.items():
            if 'washington_seasonal_multipliers' in category_config:
                seasonal_multipliers = category_config['washington_seasonal_multipliers']
                avg_multiplier = sum(seasonal_multipliers) / len(seasonal_multipliers)
                expected_inventory[category_name] = avg_multiplier
        
        # Compare actual vs expected inventory ratios
        inventory_data = {row['category_name']: float(row['avg_stock']) for row in inventory_rows}
        
        if expected_inventory and inventory_data:
            # Normalize both to relative ratios
            base_expected = min(expected_inventory.values())
            base_actual = min(inventory_data.values())
            
            for category_name in expected_inventory:
                if category_name not in inventory_data:
                    continue
                    
                total_inventory_categories += 1
                expected_ratio = expected_inventory[category_name] / base_expected
                actual_ratio = inventory_data[category_name] / base_actual
                
                # Allow 30% tolerance for inventory matching
                ratio_diff = abs(expected_ratio - actual_ratio) / expected_ratio
                if ratio_diff <= 0.3:
                    inventory_matches += 1
                    status = "✅"
                else:
                    status = "❌"
                
                logging.info(f"   {status} {category_name}:")
                logging.info(f"      Expected ratio: {expected_ratio:.2f}")
                logging.info(f"      Actual ratio:   {actual_ratio:.2f}")
                logging.info(f"      Avg stock:      {inventory_data[category_name]:.1f}")
        
        # Calculate inventory match rate
        if total_inventory_categories > 0:
            inventory_match_rate = (inventory_matches / total_inventory_categories) * 100
        
        # Test 3: Monthly order distribution
        logging.info("\n📈 MONTHLY ORDER DISTRIBUTION:")
        monthly_totals = await conn.fetch(f"""
            SELECT EXTRACT(MONTH FROM o.order_date) as month,
                   COUNT(DISTINCT o.order_id) as total_orders
            FROM {SCHEMA_NAME}.orders o
            GROUP BY EXTRACT(MONTH FROM o.order_date)
            ORDER BY month
        """)
        
        if monthly_totals:
            total_orders = sum(row['total_orders'] for row in monthly_totals)
            logging.info("   Month    Orders    % of Total")
            logging.info("   " + "-" * 30)
            for row in monthly_totals:
                month_num = int(row['month'])
                pct = (row['total_orders'] / total_orders) * 100
                logging.info(f"   {month_names[month_num-1]:<6} {row['total_orders']:>8}    {pct:>6.1f}%")
        
        # Summary
        logging.info("\n🎯 SEASONAL VERIFICATION SUMMARY:")
        if total_seasonal_categories > 0:
            order_match_rate = (seasonal_matches / total_seasonal_categories) * 100
            logging.info(f"   Order seasonality match rate: {seasonal_matches}/{total_seasonal_categories} ({order_match_rate:.1f}%)")
        
        if total_inventory_categories > 0:
            logging.info(f"   Inventory seasonality match rate: {inventory_matches}/{total_inventory_categories} ({inventory_match_rate:.1f}%)")
        
        # Overall assessment
        if total_seasonal_categories > 0 and seasonal_matches >= total_seasonal_categories * 0.7:
            logging.info("   ✅ SEASONAL PATTERNS VERIFIED: Orders follow expected seasonal trends")
        else:
            logging.info("   ⚠️  SEASONAL PATTERNS PARTIAL: Some discrepancies found in seasonal trends")
        
        if inventory_match_rate >= 70:
            logging.info("   ✅ INVENTORY SEASONALITY VERIFIED: Stock levels reflect seasonal patterns")
        else:
            logging.info("   ⚠️  INVENTORY SEASONALITY PARTIAL: Some discrepancies in seasonal stock levels")
            
    except Exception as e:
        logging.error(f"Error verifying seasonal patterns: {e}")
        raise

async def generate_postgresql_database(num_customers: int = 50000):
    """Generate complete PostgreSQL database"""
    try:
        # Create connection
        conn = await create_connection()
        
        try:
            # Drop existing tables to start fresh (optional)
            logging.info("Dropping existing tables if they exist...")
            await conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE")
            
            await create_database_schema(conn)
            await insert_stores(conn)
            await insert_categories(conn)
            await insert_product_types(conn)
            await insert_customers(conn, num_customers)
            await insert_products(conn)
            
            # Populate product embeddings from product_data.json
            logging.info("\n" + "=" * 50)
            logging.info("POPULATING PRODUCT EMBEDDINGS")
            logging.info("=" * 50)
            await populate_product_embeddings(conn, clear_existing=True)
            
            # Verify embeddings were populated
            logging.info("\n" + "=" * 50)
            logging.info("VERIFYING PRODUCT EMBEDDINGS")
            logging.info("=" * 50)
            await verify_embeddings_table(conn)
            
            # Insert inventory data
            logging.info("\n" + "=" * 50)
            logging.info("INSERTING INVENTORY DATA")
            logging.info("=" * 50)
            await insert_inventory(conn)
            
            # Insert order data
            logging.info("\n" + "=" * 50)
            logging.info("INSERTING ORDER DATA")
            logging.info("=" * 50)
            await insert_orders(conn, num_customers)
            
            # Verify the database was created and has data
            logging.info("\n" + "=" * 50)
            logging.info("FINAL DATABASE VERIFICATION")
            logging.info("=" * 50)
            await verify_database_contents(conn)
            
            # Verify seasonal patterns are working
            await verify_seasonal_patterns(conn)
            
            logging.info("\n" + "=" * 50)
            logging.info("DATABASE GENERATION COMPLETE")
            logging.info("=" * 50)
            
            logging.info("Database generation completed successfully.")
        except Exception as e:
            logging.error(f"Error during database generation: {e}")
            raise
        finally:
            await conn.close()
            logging.info("Database connection closed.")

    except Exception as e:
        logging.error(f"Failed to generate database: {e}")
        raise

async def show_database_stats():
    """Show database statistics"""
    
    logging.info("\n" + "=" * 40)
    logging.info("DATABASE STATISTICS")
    logging.info("=" * 40)
    
    conn = await create_connection()
    
    try:
        # Get table row counts
        customers_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.customers")
        products_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.products")
        orders_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.orders")
        order_items_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.order_items")
        embeddings_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.product_embeddings")
        
        # Get revenue information
        total_revenue = await conn.fetchval(f"SELECT SUM(total_amount) FROM {SCHEMA_NAME}.order_items")
        if total_revenue is None:
            total_revenue = 0
            
        # Count indexes
        index_count = await conn.fetchval(f"""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE schemaname = '{SCHEMA_NAME}' AND indexname LIKE 'idx_%'
        """)
        
        # Get database size
        db_size = await conn.fetchval(f"""
            SELECT pg_size_pretty(pg_database_size('{POSTGRES_CONFIG['database']}'))
        """)
        
        logging.info(f"Database Size: {db_size}")
        logging.info(f"Customers: {customers_count:,}")
        logging.info(f"Products: {products_count:,}")
        logging.info(f"Product Embeddings: {embeddings_count:,}")
        logging.info(f"Orders: {orders_count:,}")
        logging.info(f"Order Items: {order_items_count:,}")
        logging.info(f"Total Revenue: ${total_revenue:,.2f}")
        if orders_count > 0:
            logging.info(f"Average Order Value: ${total_revenue/orders_count:.2f}")
            logging.info(f"Orders per Customer: {orders_count/customers_count:.1f}")
            logging.info(f"Items per Order: {order_items_count/orders_count:.1f}")
        logging.info(f"Performance Indexes: {index_count}")
        
        # Show sample embeddings if they exist
        if embeddings_count > 0:
            await verify_embeddings_table(conn)
        
    finally:
        await conn.close()

async def main():
    """Main function to handle command line arguments"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Generate PostgreSQL database with product embeddings')
    parser.add_argument('--show-stats', action='store_true', 
                       help='Show database statistics instead of generating')
    parser.add_argument('--embeddings-only', action='store_true',
                       help='Only populate product embeddings (database must already exist)')
    parser.add_argument('--verify-embeddings', action='store_true',
                       help='Only verify embeddings table and show sample data')
    parser.add_argument('--verify-seasonal', action='store_true',
                       help='Only verify seasonal patterns in existing database')
    parser.add_argument('--clear-embeddings', action='store_true',
                       help='Clear existing embeddings before populating (used with --embeddings-only)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for processing embeddings (default: 100)')
    parser.add_argument('--num-customers', type=int, default=50000,
                       help='Number of customers to generate (default: 50000)')
    
    args = parser.parse_args()
    
    try:
        if args.show_stats:
            # Show database statistics
            await show_database_stats()
        elif args.verify_embeddings:
            # Verify embeddings only
            conn = await create_connection()
            try:
                await verify_embeddings_table(conn)
            finally:
                await conn.close()
        elif args.verify_seasonal:
            # Verify seasonal patterns only
            conn = await create_connection()
            try:
                await verify_seasonal_patterns(conn)
            finally:
                await conn.close()
        elif args.embeddings_only:
            # Populate embeddings only
            conn = await create_connection()
            try:
                await populate_product_embeddings(conn, clear_existing=args.clear_embeddings, batch_size=args.batch_size)
                await verify_embeddings_table(conn)
            finally:
                await conn.close()
        else:
            # Generate the complete database
            logging.info(f"Database will be created at {POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}")
            logging.info(f"Schema: {SCHEMA_NAME}")
            await generate_postgresql_database(num_customers=args.num_customers)
            
            logging.info("\nDatabase generated successfully!")
            logging.info(f"Host: {POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}")
            logging.info(f"Database: {POSTGRES_CONFIG['database']}")
            logging.info(f"Schema: {SCHEMA_NAME}")
            logging.info(f"To view statistics: python {sys.argv[0]} --show-stats")
            logging.info(f"To populate embeddings only: python {sys.argv[0]} --embeddings-only")
            logging.info(f"To verify embeddings: python {sys.argv[0]} --verify-embeddings")
            logging.info(f"To verify seasonal patterns: python {sys.argv[0]} --verify-seasonal")
            
    except Exception as e:
        logging.error(f"Failed to complete operation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check if required packages are available
    try:
        from dotenv import load_dotenv
        from faker import Faker
    except ImportError as e:
        logging.error(f"Required library not found: {e}")
        logging.error("Please install required packages with: pip install -r requirements_postgres.txt")
        exit(1)
    
    asyncio.run(main())
