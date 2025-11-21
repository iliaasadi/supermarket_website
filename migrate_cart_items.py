"""
Migration script to add created_at and updated_at columns to cart_item table.
Run this once to update existing databases.
"""
from app import app, db
from sqlalchemy import text

def migrate_cart_items():
    """Add created_at and updated_at columns to cart_item table if they don't exist"""
    with app.app_context():
        try:
            # Check if column exists by trying to query it
            db.session.execute(text("SELECT created_at FROM cart_item LIMIT 1"))
            print("Columns already exist. No migration needed.")
        except Exception:
            # Column doesn't exist, add it
            try:
                print("Adding created_at and updated_at columns to cart_item table...")
                # SQLite doesn't support CURRENT_TIMESTAMP in ALTER TABLE, so we add without default
                db.session.execute(text("ALTER TABLE cart_item ADD COLUMN created_at DATETIME"))
                db.session.execute(text("ALTER TABLE cart_item ADD COLUMN updated_at DATETIME"))
                # Update existing rows with current timestamp
                from datetime import datetime
                now = datetime.now().isoformat()
                db.session.execute(text("UPDATE cart_item SET created_at = :now, updated_at = :now WHERE created_at IS NULL"), {"now": now})
                db.session.commit()
                print("Migration completed successfully!")
            except Exception as e:
                db.session.rollback()
                print(f"Error during migration: {e}")
                print("You may need to delete the database and recreate it.")

if __name__ == '__main__':
    migrate_cart_items()

