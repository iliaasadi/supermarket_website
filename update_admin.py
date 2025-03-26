from app import app, db
from models import User

def update_admin():
    with app.app_context():
        # First, try to find the existing admin
        admin = User.query.filter_by(is_admin=True).first()
        
        if admin:
            # Update existing admin
            admin.phone_number = '+989145519029'
            admin.set_password('09145519029')
            print("Updated existing admin user")
        else:
            # Create new admin if none exists
            admin = User(
                username='Admin',
                phone_number='+989145519029',
                is_admin=True,
                is_verified=True
            )
            admin.set_password('09145519029')
            db.session.add(admin)
            print("Created new admin user")
        
        try:
            db.session.commit()
            print("Admin user updated successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating admin user: {str(e)}")

if __name__ == "__main__":
    update_admin() 