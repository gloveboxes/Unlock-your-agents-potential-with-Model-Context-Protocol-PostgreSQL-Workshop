"""
Customer Sales Database Generator

This script generates a comprehensive customer sales database with optimized indexing.

DATA FILE STRUCTURE:
- product_data.json: Contains all product information (main_categories with products)
- reference_data.json: Contains store configurations (weights, year weights)
"""

import os
import random
import sqlite3
import logging
import json
import datetime
import sys
import time
from faker import Faker

# Initialize Faker and logging
fake = Faker()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def create_database_schema(conn):
    """Create database tables and indexes"""
    try:
        cursor = conn.cursor()
        
        # Create stores table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stores (
                store_id INTEGER PRIMARY KEY,
                store_name TEXT UNIQUE NOT NULL
            )
        """)
        
        # Create customers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT
            )
        """)
        
        # Create categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                category_id INTEGER PRIMARY KEY,
                category_name TEXT NOT NULL UNIQUE
            )
        """)
        
        # Create product_types table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_types (
                type_id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                type_name TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories (category_id)
            )
        """)
        
        # Create products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY,
                sku TEXT UNIQUE NOT NULL,
                product_name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                type_id INTEGER NOT NULL,
                base_price REAL NOT NULL,
                product_description TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories (category_id),
                FOREIGN KEY (type_id) REFERENCES product_types (type_id)
            )
        """)
        
        # Create inventory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                store_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stock_level INTEGER NOT NULL,
                PRIMARY KEY (store_id, product_id),
                FOREIGN KEY (store_id) REFERENCES stores (store_id),
                FOREIGN KEY (product_id) REFERENCES products (product_id)
            )
        """)
        
        # Create orders table (header only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                store_id INTEGER NOT NULL,
                order_date DATE NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
                FOREIGN KEY (store_id) REFERENCES stores (store_id)
            )
        """)
        
        # Create order_items table (line items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                order_item_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                discount_percent INTEGER DEFAULT 0,
                discount_amount REAL DEFAULT 0,
                total_amount REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders (order_id),
                FOREIGN KEY (product_id) REFERENCES products (product_id)
            )
        """)
        
        # Create optimized performance indexes
        logging.info("Creating performance indexes...")
        
        # Category and type indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(category_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_types_category ON product_types(category_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_product_types_name ON product_types(type_name)")
        
        # Product indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_type ON products(type_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON products(base_price)")
        
        # Inventory indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_store_product ON inventory(store_id, product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_store ON inventory(store_id)")
        
        # Store indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_name ON stores(store_name)")
        
        # Order indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_store ON orders(store_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_date ON orders(customer_id, order_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_store_date ON orders(store_id, order_date)")
        
        # Order items indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_total ON order_items(total_amount)")
        
        # Covering indexes for aggregation queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_covering ON order_items(order_id, product_id, total_amount, quantity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_covering ON products(category_id, type_id, product_id, sku, base_price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_sku_covering ON products(sku, product_id, product_name, base_price)")
        
        # Customer indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email)")
        
        conn.commit()
        logging.info("Performance indexes created successfully!")
        logging.info("Database schema created successfully!")
    except sqlite3.Error as e:
        logging.error(f"Error creating database schema: {e}")
        raise

def batch_insert(cursor, query, data, batch_size=1000):
    """Insert data in batches"""
    for i in range(0, len(data), batch_size):
        cursor.executemany(query, data[i:i + batch_size])

def insert_customers(conn, num_customers=100000):
    """Insert customer data into the database"""
    try:
        cursor = conn.cursor()
        
        logging.info(f"Generating {num_customers:,} customers...")
        
        customers_data = []
        
        for i in range(1, num_customers + 1):
            first_name = fake.first_name().replace("'", "''")  # Escape single quotes
            last_name = fake.last_name().replace("'", "''")
            email = f"{first_name.lower()}.{last_name.lower()}.{i}@example.com"
            phone = generate_phone_number()
            
            customers_data.append((first_name, last_name, email, phone))
        
        batch_insert(cursor, "INSERT INTO customers (first_name, last_name, email, phone) VALUES (?, ?, ?, ?)", customers_data)
        
        conn.commit()
        logging.info(f"Successfully inserted {num_customers:,} customers!")
    except sqlite3.Error as e:
        logging.error(f"Error inserting customers: {e}")
        raise

def insert_products(conn):
    """Insert product data into the database"""
    try:
        cursor = conn.cursor()
        
        logging.info("Generating products...")
        
        # Get category and type mappings
        cursor.execute("SELECT category_id, category_name FROM categories")
        category_mapping = {name: id for id, name in cursor.fetchall()}
        
        cursor.execute("SELECT type_id, type_name, category_id FROM product_types")
        type_mapping = {(cat_id, type_name): type_id for type_id, type_name, cat_id in cursor.fetchall()}
        
        products_data = []
        product_id = 1
        
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
                    sku = product_details.get("sku", f"SKU{product_id:06d}")  # Fallback if no SKU
                    fixed_price = product_details["price"]
                    description = product_details["description"]
                    base_price = float(fixed_price)
                    products_data.append((product_id, sku, product_name, category_id, type_id, base_price, description))
                    product_id += 1
        
        batch_insert(cursor, "INSERT INTO products (product_id, sku, product_name, category_id, type_id, base_price, product_description) VALUES (?, ?, ?, ?, ?, ?, ?)", products_data)
        
        conn.commit()
        logging.info(f"Successfully inserted {len(products_data):,} products!")
        return product_id - 1  # Return the last product_id used
    except sqlite3.Error as e:
        logging.error(f"Error inserting products: {e}")
        raise

def insert_stores(conn):
    """Insert store data into the database"""
    try:
        cursor = conn.cursor()
        
        logging.info("Generating stores...")
        
        stores_data = []
        store_id = 1
        
        for store_name, store_config in stores.items():
            stores_data.append((store_id, store_name))
            store_id += 1
        
        batch_insert(cursor, "INSERT INTO stores (store_id, store_name) VALUES (?, ?)", stores_data)
        
        conn.commit()
        logging.info(f"Successfully inserted {len(stores_data):,} stores!")
        return store_id - 1  # Return the last store_id used
    except sqlite3.Error as e:
        logging.error(f"Error inserting stores: {e}")
        raise

def insert_categories(conn):
    """Insert category data into the database"""
    try:
        cursor = conn.cursor()
        
        logging.info("Generating categories...")
        
        categories_data = []
        category_id = 1
        
        # Extract unique categories from product data
        for main_category in main_categories.keys():
            categories_data.append((category_id, main_category))
            category_id += 1
        
        batch_insert(cursor, "INSERT INTO categories (category_id, category_name) VALUES (?, ?)", categories_data)
        
        conn.commit()
        logging.info(f"Successfully inserted {len(categories_data):,} categories!")
        return category_id - 1  # Return the last category_id used
    except sqlite3.Error as e:
        logging.error(f"Error inserting categories: {e}")
        raise

def insert_product_types(conn):
    """Insert product type data into the database"""
    try:
        cursor = conn.cursor()
        
        logging.info("Generating product types...")
        
        product_types_data = []
        type_id = 1
        
        # Get category_id mapping
        cursor.execute("SELECT category_id, category_name FROM categories")
        category_mapping = {name: id for id, name in cursor.fetchall()}
        
        # Extract product types for each category
        for main_category, subcategories in main_categories.items():
            category_id = category_mapping[main_category]
            for subcategory in subcategories.keys():
                # Skip the seasonal multipliers key
                if subcategory == 'washington_seasonal_multipliers':
                    continue
                
                product_types_data.append((type_id, category_id, subcategory))
                type_id += 1
        
        batch_insert(cursor, "INSERT INTO product_types (type_id, category_id, type_name) VALUES (?, ?, ?)", product_types_data)
        
        conn.commit()
        logging.info(f"Successfully inserted {len(product_types_data):,} product types!")
        return type_id - 1  # Return the last type_id used
    except sqlite3.Error as e:
        logging.error(f"Error inserting product types: {e}")
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

def insert_orders(conn, num_customers=100000, max_product_id=1, product_lookup=None):
    """Insert order data into the database with separate orders and order_items tables"""
    cursor = conn.cursor()
    
    # Build product lookup if not provided
    if product_lookup is None:
        product_lookup = build_product_lookup()
    
    logging.info(f"Generating orders for {num_customers:,} customers...")
    
    batch_size = 1000
    orders_data = []
    order_items_data = []
    order_id = 1
    order_item_id = 1
    total_orders = 0
    
    for customer_id in range(1, num_customers + 1):
        # Generate random number of orders for this customer
        base_orders = random.randint(2, 8)
        
        for _ in range(base_orders):
            # Choose a random store for this order
            store_name = weighted_store_choice()
            store_id = get_store_id_by_name(conn, store_name)
            
            # Generate weighted year and random date within that year
            order_year = weighted_year_choice()
            start_of_year = datetime.date(order_year, 1, 1)
            end_of_year = datetime.date(order_year, 12, 31)
            days_in_year = (end_of_year - start_of_year).days
            random_days = random.randint(0, days_in_year)
            order_date = start_of_year + datetime.timedelta(days=random_days)
            
            # Create the order header
            orders_data.append((order_id, customer_id, store_id, order_date.isoformat()))
            
            # Generate 1-3 items for this order
            num_items = random.randint(1, 3)
            
            for _ in range(num_items):
                # Choose product with seasonal weighting based on order month
                main_category = choose_seasonal_product_category(order_date.month)
                product_type = choose_product_type(main_category)
                
                # Get product list for this category and type
                product_list = main_categories[main_category][product_type]
                if not product_list:  # Skip if empty product list
                    continue
                    
                # Choose a random product from the list
                product_info = random.choice(product_list)
                product_name = product_info["name"]
                fixed_price = product_info["price"]
                
                # Get the product_id from lookup
                lookup_key = (main_category, product_type, product_name)
                product_id = product_lookup.get(lookup_key)
                if product_id is None:
                    logging.warning(f"Product not found in lookup: {lookup_key}")
                    continue
                
                quantity = random.randint(1, 5)
                
                # Calculate pricing
                unit_price = float(fixed_price)
                discount_percent = random.randint(0, 15)  # 0-15% discount
                discount_amount = round((unit_price * quantity * discount_percent) / 100, 2)
                total_amount = (unit_price * quantity) - discount_amount
                
                order_items_data.append((
                    order_item_id, order_id, product_id, quantity, unit_price,
                    discount_percent, discount_amount, total_amount
                ))
                order_item_id += 1
            
            order_id += 1
            total_orders += 1
            
            # Insert in batches
            if len(orders_data) >= batch_size:
                cursor.executemany(
                    """INSERT INTO orders (order_id, customer_id, store_id, order_date) 
                       VALUES (?, ?, ?, ?)""",
                    orders_data
                )
                cursor.executemany(
                    """INSERT INTO order_items (order_item_id, order_id, product_id, quantity, unit_price,
                       discount_percent, discount_amount, total_amount) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    order_items_data
                )
                orders_data = []
                order_items_data = []
                
                if total_orders % 50000 == 0:
                    logging.info(f"  Inserted {total_orders:,} orders...")
                    conn.commit()
    
    # Insert remaining orders and items
    if orders_data:
        cursor.executemany(
            """INSERT INTO orders (order_id, customer_id, store_id, order_date) 
               VALUES (?, ?, ?, ?)""",
            orders_data
        )
    if order_items_data:
        cursor.executemany(
            """INSERT INTO order_items (order_item_id, order_id, product_id, quantity, unit_price,
               discount_percent, discount_amount, total_amount) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            order_items_data
        )
    
    conn.commit()
    logging.info(f"Successfully inserted {total_orders:,} orders!")
    logging.info(f"Successfully inserted {order_item_id - 1:,} order items!")

def insert_inventory(conn):
    """Insert inventory data distributed across stores based on customer distribution weights"""
    try:
        cursor = conn.cursor()
        
        logging.info("Generating inventory distribution across stores...")
        
        inventory_data = []
        store_names = list(stores.keys())
        
        # Get total distribution weight to calculate proportions
        total_weight = sum(stores[store]['customer_distribution_weight'] for store in store_names)
        
        # Get product data with stock levels
        product_id = 1
        total_inventory_records = 0
        
        for main_category, subcategories in main_categories.items():
            for subcategory, product_list in subcategories.items():
                # Skip the seasonal multipliers key, only process actual product types
                if subcategory == 'washington_seasonal_multipliers':
                    continue
                    
                if not product_list:  # Handle empty product lists
                    continue
                    
                for product_details in product_list:
                    if 'stock_level' in product_details:
                        total_stock = product_details["stock_level"]
                        
                        # Distribute stock across stores based on customer distribution weights
                        remaining_stock = total_stock
                        
                        for i, store_name in enumerate(store_names):
                            store_id = get_store_id_by_name(conn, store_name)
                            weight = stores[store_name]['customer_distribution_weight']
                            weight_proportion = weight / total_weight
                            
                            if i == len(store_names) - 1:
                                # Last store gets remaining stock to ensure total is preserved
                                store_stock = remaining_stock
                            else:
                                # Calculate proportional stock for this store
                                store_stock = max(0, int(total_stock * weight_proportion))
                                remaining_stock -= store_stock
                            
                            inventory_data.append((store_id, product_id, store_stock))
                            total_inventory_records += 1
                    
                    product_id += 1
        
        batch_insert(cursor, "INSERT INTO inventory (store_id, product_id, stock_level) VALUES (?, ?, ?)", inventory_data)
        
        conn.commit()
        logging.info(f"Successfully inserted {total_inventory_records:,} inventory records across {len(store_names)} stores!")
        
        # Show inventory distribution summary
        logging.info("📦 Inventory distribution by store:")
        for store_name in store_names:
            store_id = get_store_id_by_name(conn, store_name)
            cursor.execute("SELECT SUM(stock_level) FROM inventory WHERE store_id = ?", (store_id,))
            total_stock = cursor.fetchone()[0] or 0
            weight = stores[store_name]['customer_distribution_weight']
            logging.info(f"   {store_name}: {total_stock:,} units (weight: {weight})")
            
    except sqlite3.Error as e:
        logging.error(f"Error inserting inventory: {e}")
        raise

def generate_sqlite_database(db_path="zava_retail.db", num_customers=50000):
    """Generate complete SQLite database"""
    try:
        # Convert to absolute path
        abs_db_path = os.path.abspath(db_path)
        
        # Remove existing database if it exists
        if os.path.exists(abs_db_path):
            os.remove(abs_db_path)
            logging.info(f"Existing database at {abs_db_path} removed.")

        # Create new database connection
        conn = sqlite3.connect(abs_db_path)
        logging.info(f"Database created at {abs_db_path}.")

        try:
            create_database_schema(conn)
            insert_stores(conn)
            insert_categories(conn)
            insert_product_types(conn)
            insert_customers(conn, num_customers)
            max_product_id = insert_products(conn)
            insert_inventory(conn)
            
            # Build product lookup for order generation
            product_lookup = build_product_lookup()
            insert_orders(conn, num_customers, max_product_id, product_lookup)
            
            # Verify the database was created and has data
            verify_database_contents(conn)
            
            logging.info("Database generation completed successfully.")
        except Exception as e:
            logging.error(f"Error during database generation: {e}")
            raise
        finally:
            conn.close()
            logging.info("Database connection closed.")
            
        # Final verification that file exists
        if os.path.exists(abs_db_path):
            file_size = os.path.getsize(abs_db_path)
            logging.info(f"✅ Database saved successfully at: {abs_db_path}")
            logging.info(f"📊 Database file size: {file_size / (1024*1024):.2f} MB")
        else:
            logging.error(f"❌ Database file was not created at: {abs_db_path}")

    except Exception as e:
        logging.error(f"Failed to generate database: {e}")
        raise

def verify_database_contents(conn):
    """Verify database contents and show key statistics"""
    cursor = conn.cursor()
    
    logging.info("\n" + "=" * 60)
    logging.info("DATABASE VERIFICATION & STATISTICS")
    logging.info("=" * 60)
    
    # Store distribution verification
    logging.info("\n🏪 STORE SALES DISTRIBUTION:")
    cursor.execute("""
        SELECT s.store_name, 
               COUNT(o.order_id) as orders,
               printf('$%.1fM', SUM(oi.total_amount)/1000000.0) as revenue,
               printf('%.1f%%', 100.0 * COUNT(o.order_id) / (SELECT COUNT(*) FROM orders)) as order_pct
        FROM orders o 
        JOIN stores s ON o.store_id = s.store_id
        JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY s.store_id, s.store_name
        ORDER BY SUM(oi.total_amount) DESC
    """)
    
    logging.info("   Store               Orders     Revenue    % of Orders")
    logging.info("   " + "-" * 50)
    for row in cursor.fetchall():
        logging.info(f"   {row[0]:<18} {row[1]:>8,} {row[2]:>10} {row[3]:>10}")
    
    # Year-over-year growth verification
    logging.info("\n📈 YEAR-OVER-YEAR GROWTH PATTERN:")
    cursor.execute("""
        SELECT SUBSTR(o.order_date, 1, 4) as year,
               COUNT(DISTINCT o.order_id) as orders,
               printf('$%.1fM', SUM(oi.total_amount)/1000000.0) as revenue,
               LAG(SUM(oi.total_amount)) OVER (ORDER BY SUBSTR(o.order_date, 1, 4)) as prev_revenue
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY SUBSTR(o.order_date, 1, 4)
        ORDER BY year
    """)
    
    logging.info("   Year    Orders     Revenue    Growth")
    logging.info("   " + "-" * 35)
    results = cursor.fetchall()
    for i, row in enumerate(results):
        year, orders, revenue, prev_revenue = row
        if prev_revenue:
            growth = ((float(revenue.replace('$', '').replace('M', '')) - 
                      float(prev_revenue)) / float(prev_revenue)) * 100
            growth_str = f"{growth:+.1f}%"
        else:
            growth_str = "Base"
        logging.info(f"   {year}   {orders:>8,} {revenue:>10} {growth_str:>8}")
    
    # Product category distribution
    logging.info("\n🛍️  TOP PRODUCT CATEGORIES:")
    cursor.execute("""
        SELECT c.category_name,
               COUNT(DISTINCT o.order_id) as orders,
               printf('$%.1fM', SUM(oi.total_amount)/1000000.0) as revenue
        FROM categories c
        JOIN products p ON c.category_id = p.category_id
        JOIN order_items oi ON p.product_id = oi.product_id
        JOIN orders o ON oi.order_id = o.order_id
        GROUP BY c.category_id, c.category_name
        ORDER BY SUM(oi.total_amount) DESC
        LIMIT 5
    """)
    
    logging.info("   Category             Orders     Revenue")
    logging.info("   " + "-" * 40)
    for row in cursor.fetchall():
        logging.info(f"   {row[0]:<18} {row[1]:>8,} {row[2]:>10}")
    
    # Database performance test
    logging.info("\n⚡ QUERY PERFORMANCE TEST:")
    
    test_queries = [
        ("Store aggregation", "SELECT s.store_name, COUNT(DISTINCT o.order_id), SUM(oi.total_amount) FROM orders o JOIN stores s ON o.store_id = s.store_id JOIN order_items oi ON o.order_id = oi.order_id GROUP BY s.store_id, s.store_name"),
        ("Yearly trend", "SELECT SUBSTR(o.order_date, 1, 4), COUNT(DISTINCT o.order_id), SUM(oi.total_amount) FROM orders o JOIN order_items oi ON o.order_id = oi.order_id GROUP BY SUBSTR(o.order_date, 1, 4)"),
        ("Customer order history", "SELECT customer_id, COUNT(*), MAX(order_date) FROM orders WHERE customer_id <= 100 GROUP BY customer_id"),
    ]
    
    for query_name, query in test_queries:
        start_time = time.time()
        cursor.execute(query)
        results = cursor.fetchall()
        elapsed = time.time() - start_time
        logging.info(f"   {query_name:<20}: {elapsed:.3f}s ({len(results)} rows)")
    
    # Index verification
    logging.info("\n🗂️  DATABASE INDEXES:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    indexes = [row[0] for row in cursor.fetchall()]
    logging.info(f"   Created {len(indexes)} performance indexes")
    
    # Final summary
    cursor.execute("SELECT COUNT(*) FROM customers")
    customers = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM products")  
    products = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders")
    orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM order_items")
    order_items = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_amount) FROM order_items")
    total_revenue = cursor.fetchone()[0]
    
    logging.info("\n✅ DATABASE SUMMARY:")
    logging.info(f"   Customers:     {customers:>8,}")
    logging.info(f"   Products:      {products:>8,}")
    logging.info(f"   Orders:        {orders:>8,}")
    logging.info(f"   Order Items:   {order_items:>8,}")
    logging.info(f"   Total Revenue: ${total_revenue/1000000:.1f}M")
    logging.info(f"   Avg Order:     ${total_revenue/orders:.2f}")
    logging.info(f"   Orders/Customer: {orders/customers:.1f}")
    logging.info(f"   Items/Order: {order_items/orders:.1f}")
    
    # Show seasonal trends analysis
    show_seasonal_trends_analysis(conn)


def show_database_stats(db_path="../zava_retail.db"):
    """Show database statistics"""
    
    logging.info("\n" + "=" * 40)
    logging.info("DATABASE STATISTICS")
    logging.info("=" * 40)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get database size
    db_size = os.path.getsize(db_path) / (1024*1024)  # Convert to MB
    
    # Get table row counts
    cursor.execute("SELECT COUNT(*) FROM customers")
    customers_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM products") 
    products_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    orders_count = cursor.fetchone()[0]
    
    # Count indexes
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'")
    index_count = cursor.fetchone()[0]
    
    logging.info(f"Database Size: {db_size:.1f} MB")
    logging.info(f"Customers: {customers_count:,}")
    logging.info(f"Products: {products_count:,}")
    logging.info(f"Orders: {orders_count:,}")
    logging.info(f"Indexes: {index_count}")
    
    conn.close()

def choose_product_category():
    """Choose a category with equal weights"""
    categories = list(main_categories.keys())
    return random.choice(categories)

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
        # Skip the seasonal multipliers key, only include actual product types
        if key != 'washington_seasonal_multipliers':
            product_types.append(key)
    
    if not product_types:
        return None
    return random.choice(product_types)

def build_product_lookup():
    """Build a lookup table mapping (main_category, product_type, product_name) to product_id"""
    product_lookup = {}
    product_id = 1
    
    for main_category, subcategories in main_categories.items():
        for product_type, product_list in subcategories.items():
            # Skip the seasonal multipliers key, only process actual product types
            if product_type == 'washington_seasonal_multipliers':
                continue
                
            if not product_list:  # Handle empty product lists
                continue
                
            for product_details in product_list:
                product_name = product_details["name"]
                key = (main_category, product_type, product_name)
                product_lookup[key] = product_id
                product_id += 1
    
    return product_lookup

def show_seasonal_trends_analysis(conn):
    """Show seasonal sales trends analysis to verify the seasonal multipliers are working"""
    cursor = conn.cursor()
    
    logging.info("\n🌦️  SEASONAL TRENDS ANALYSIS:")
    
    # Monthly sales by category for categories with seasonal multipliers
    seasonal_categories = []
    for category_name, category_data in main_categories.items():
        if 'washington_seasonal_multipliers' in category_data:
            seasonal_categories.append(category_name)
    
    if seasonal_categories:
        logging.info("   Monthly sales distribution for categories with seasonal trends:")
        logging.info("   " + "-" * 80)
        
        for category in seasonal_categories[:3]:  # Show first 3 categories to avoid too much output
            # Get expected multipliers
            expected_multipliers = main_categories[category]['washington_seasonal_multipliers']
            
            cursor.execute("""
                SELECT CAST(SUBSTR(o.order_date, 6, 2) AS INTEGER) as month,
                       COUNT(DISTINCT o.order_id) as orders,
                       printf('%.2f', AVG(oi.total_amount)) as avg_order
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                JOIN products p ON oi.product_id = p.product_id
                JOIN categories c ON p.category_id = c.category_id
                WHERE c.category_name = ?
                GROUP BY CAST(SUBSTR(o.order_date, 6, 2) AS INTEGER)
                ORDER BY month
            """, (category,))
            
            results = cursor.fetchall()
            logging.info(f"\n   {category}:")
            logging.info("   Month  Orders  Avg$   Expected Multiplier  Actual vs Expected")
            logging.info("   " + "-" * 65)
            
            if results:
                # Calculate base average (assuming equal distribution would be total/12)
                total_orders = sum(row[1] for row in results)
                base_orders = total_orders / 12
                
                for month, orders, avg_order in results:
                    expected_mult = expected_multipliers[month - 1]
                    actual_mult = orders / base_orders if base_orders > 0 else 0
                    variance = ((actual_mult - expected_mult) / expected_mult * 100) if expected_mult > 0 else 0
                    
                    logging.info(f"   {month:>2}     {orders:>5}  {avg_order:>6}        {expected_mult:>4.1f}x           {actual_mult:4.1f}x ({variance:+5.1f}%)")

def get_store_id_by_name(conn, store_name):
    """Get store_id for a given store name"""
    cursor = conn.cursor()
    cursor.execute("SELECT store_id FROM stores WHERE store_name = ?", (store_name,))
    result = cursor.fetchone()
    return result[0] if result else 1  # Default to store_id 1 if not found

if __name__ == "__main__":
    # Check if faker is available
    try:
        from faker import Faker
    except ImportError:
        logging.error("faker library not found. Please install it with: pip install faker")
        exit(1)
    
    import sys
    
    # Check for command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--show-stats":
        # Show database statistics
        db_path = "../zava_retail.db"
        if os.path.exists(db_path):
            show_database_stats(db_path)
        else:
            logging.error(f"Database not found: {db_path}")
            logging.info("Run without arguments to generate the database first.")
    else:
        # Generate the database
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zava_retail.db")
        abs_path = os.path.abspath(db_path)
        logging.info(f"Database will be created at: {abs_path}")
        generate_sqlite_database(db_path, num_customers=50000)
        
        logging.info("\nDatabase generated successfully!")
        logging.info(f"Location: {abs_path}")
        logging.info(f"To view statistics: python {sys.argv[0]} --show-stats")