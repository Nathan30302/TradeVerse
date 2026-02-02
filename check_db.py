import sqlite3

# Connect to the database
conn = sqlite3.connect('tradeverse.db')
cursor = conn.cursor()

# Check the schema of the users table
cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()

print("Users table columns:")
for col in columns:
    print(f"  {col[1]}: {col[2]}")

conn.close()
