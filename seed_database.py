"""
Database-agnostic seed script.
"""
from sqlalchemy import (
    Column, Date, Float, ForeignKey, Integer, MetaData, String, Table,
)

from app.db.database_service import get_engine

metadata = MetaData()

customers = Table(
    "customers", metadata,
    Column("customer_id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100)),
    Column("email", String(100)),
    Column("city", String(50)),
    Column("join_date", String(20)),
)

products = Table(
    "products", metadata,
    Column("product_id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100)),
    Column("category", String(50)),
    Column("price", Float),
)

orders = Table(
    "orders", metadata,
    Column("order_id", Integer, primary_key=True, autoincrement=True),
    Column("customer_id", Integer, ForeignKey("customers.customer_id")),
    Column("order_date", String(20)),
    Column("total_amount", Float),
)

order_items = Table(
    "order_items", metadata,
    Column("order_item_id", Integer, primary_key=True, autoincrement=True),
    Column("order_id", Integer, ForeignKey("orders.order_id")),
    Column("product_id", Integer, ForeignKey("products.product_id")),
    Column("quantity", Integer),
    Column("subtotal", Float),
)


def seed():
    engine = get_engine()
    print(f"Seeding database: {engine.url.render_as_string(hide_password=True)}")

    metadata.drop_all(engine)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(customers.insert(), [
            {"name": "Alice Johnson", "email": "alice@example.com", "city": "New York", "join_date": "2024-01-10"},
            {"name": "Bob Smith", "email": "bob@example.com", "city": "Los Angeles", "join_date": "2024-02-14"},
            {"name": "Charlie Lee", "email": "charlie@example.com", "city": "Chicago", "join_date": "2024-03-01"},
            {"name": "Diana King", "email": "diana@example.com", "city": "Houston", "join_date": "2024-04-20"},
        ])

        conn.execute(products.insert(), [
            {"name": "Wireless Mouse", "category": "Electronics", "price": 25.99},
            {"name": "Laptop Sleeve", "category": "Accessories", "price": 15.49},
            {"name": "Bluetooth Headphones", "category": "Electronics", "price": 45.99},
            {"name": "Water Bottle", "category": "Home & Kitchen", "price": 12.00},
            {"name": "Notebook", "category": "Stationery", "price": 3.50},
        ])

        conn.execute(orders.insert(), [
            {"customer_id": 1, "order_date": "2024-05-05", "total_amount": 83.47},
            {"customer_id": 2, "order_date": "2024-05-07", "total_amount": 15.49},
            {"customer_id": 3, "order_date": "2024-06-02", "total_amount": 57.99},
            {"customer_id": 1, "order_date": "2024-06-10", "total_amount": 12.00},
        ])

        conn.execute(order_items.insert(), [
            {"order_id": 1, "product_id": 1, "quantity": 2, "subtotal": 51.98},
            {"order_id": 1, "product_id": 3, "quantity": 1, "subtotal": 45.99},
            {"order_id": 2, "product_id": 2, "quantity": 1, "subtotal": 15.49},
            {"order_id": 3, "product_id": 3, "quantity": 1, "subtotal": 45.99},
            {"order_id": 3, "product_id": 5, "quantity": 2, "subtotal": 7.00},
            {"order_id": 4, "product_id": 4, "quantity": 1, "subtotal": 12.00},
        ])

    print("Seed complete: customers, products, orders, order_items populated.")


if __name__ == "__main__":
    seed()
