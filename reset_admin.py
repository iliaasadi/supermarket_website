from app import app, db
from models import User, Wallet, Address, StoreLocation, Order, OrderItem, CartItem, WalletTransaction
from werkzeug.security import generate_password_hash

def reset_admin():
    with app.app_context():
        # Delete all data in the correct order to handle foreign key constraints
        OrderItem.query.delete()
        Order.query.delete()
        CartItem.query.delete()
        WalletTransaction.query.delete()
        Wallet.query.delete()
        Address.query.delete()
        User.query.delete()
        StoreLocation.query.delete()
        db.session.commit()
        print("All data deleted successfully!")

        # Create new admin user
        admin = User(
            username='Admin',
            phone_number='+989145519029',  # Format the phone number
            is_admin=True,
            is_verified=True
        )
        admin.set_password('09145519029')
        db.session.add(admin)
        db.session.commit()
        print("New admin user created successfully!")

        # Create wallet for admin
        admin_wallet = Wallet(user_id=admin.id, balance=0.0)
        db.session.add(admin_wallet)
        db.session.commit()
        print("Admin wallet created successfully!")

        # Create admin's address
        admin_address = Address(
            user_id=admin.id,
            street='ورزی شمالی',
            tag='خانه',
            building_unit_number='1',
            description='آدرس اصلی',
            is_default=True
        )
        db.session.add(admin_address)
        db.session.commit()
        print("Admin address created successfully!")

        # Create supermarket location
        store_location = StoreLocation(
            name='Deniz Supermarket',
            address='ورزی شمالی',
            description='فروشگاه اصلی دنیز',
            is_active=True
        )
        db.session.add(store_location)
        db.session.commit()
        print("Store location created successfully!")

if __name__ == '__main__':
    reset_admin() 