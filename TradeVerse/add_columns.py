import sqlite3

# Connect to the database
conn = sqlite3.connect('tradeverse.db')
cursor = conn.cursor()

# Add the missing columns to the users table
try:
    cursor.execute("ALTER TABLE users ADD COLUMN subscription_tier TEXT DEFAULT 'free'")
    print("Added subscription_tier column")
except sqlite3.OperationalError as e:
    print(f"subscription_tier column might already exist: {e}")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN subscription_status TEXT DEFAULT 'active'")
    print("Added subscription_status column")
except sqlite3.OperationalError as e:
    print(f"subscription_status column might already exist: {e}")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN trial_ends_at DATETIME")
    print("Added trial_ends_at column")
except sqlite3.OperationalError as e:
    print(f"trial_ends_at column might already exist: {e}")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN subscription_expires_at DATETIME")
    print("Added subscription_expires_at column")
except sqlite3.OperationalError as e:
    print(f"subscription_expires_at column might already exist: {e}")

try:
    cursor.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
    print("Added stripe_customer_id column")
except sqlite3.OperationalError as e:
    print(f"stripe_customer_id column might already exist: {e}")

# Commit the changes
conn.commit()
conn.close()

print("Database schema updated successfully!")
