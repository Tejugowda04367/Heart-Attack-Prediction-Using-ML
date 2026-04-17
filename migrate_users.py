import sqlite3
from pymongo import MongoClient

# --- 1. Connect to SQLite ---
sqlite_path = r"C:\Users\tejug\OneDrive\Desktop\heart_attack_prediction_using_ML\users.db"
sqlite_conn = sqlite3.connect(sqlite_path)
cursor = sqlite_conn.cursor()

# --- 2. Connect to MongoDB ---
client = MongoClient("mongodb://localhost:27017/")
mongo_db = client["heart_attack_db"]

# --- 3. Get all tables in SQLite ---
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for table in tables:
    table_name = table[0]
    collection = mongo_db[table_name]  # Create separate collection per table
    print(f"📥 Migrating table: {table_name}")

    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]

    for row in rows:
        document = dict(zip(columns, row))  # Convert row to dictionary
        collection.insert_one(document)

print("✅ Migration completed! Check MongoDB Compass or run `mongosh` to verify data.")
sqlite_conn.close()
