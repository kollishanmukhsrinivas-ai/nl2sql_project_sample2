import sqlite3


# Step1: Create Dummy database

conn = sqlite3.connect('amazon.db')
cursor = conn.cursor()

# Step2: Create Tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    city TEXT,
    join_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    price REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    order_date TEXT,
    total_amount REAL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    subtotal REAL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
)
""")

customers = [
    ('Alice Johnson', 'alice@example.com', 'New York', '2024-01-10'),
    ('Bob Smith', 'bob@example.com', 'Los Angeles', '2024-02-14'),
    ('Charlie Lee', 'charlie@example.com', 'Chicago', '2024-03-01'),
    ('Diana King', 'diana@example.com', 'Houston', '2024-04-20')
]
cursor.executemany("INSERT INTO customers (name, email, city, join_date) VALUES (?, ?, ?, ?)", customers)

products = [
    ('Wireless Mouse', 'Electronics', 25.99),
    ('Laptop Sleeve', 'Accessories', 15.49),
    ('Bluetooth Headphones', 'Electronics', 45.99),
    ('Water Bottle', 'Home & Kitchen', 12.00),
    ('Notebook', 'Stationery', 3.50)
]
cursor.executemany("INSERT INTO products (name, category, price) VALUES (?, ?, ?)", products)

orders = [
    (1, '2024-05-05', 83.47),
    (2, '2024-05-07', 15.49),
    (3, '2024-06-02', 57.99),
    (1, '2024-06-10', 12.00)
]
cursor.executemany("INSERT INTO orders (customer_id, order_date, total_amount) VALUES (?, ?, ?)", orders)

order_items = [
    (1, 1, 2, 25.99 * 2),
    (1, 3, 1, 45.99),
    (2, 2, 1, 15.49),
    (3, 3, 1, 45.99),
    (3, 5, 2, 3.50 * 2),
    (4, 4, 1, 12.00)
]
cursor.executemany("INSERT INTO order_items (order_id, product_id, quantity, subtotal) VALUES (?, ?, ?, ?)", order_items)

conn.commit()
conn.close()

print("✅ Database 'amazon.db' created with dummy data!")