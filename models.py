from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from datetime import datetime, timedelta

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128))
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    profile_picture = db.Column(db.String(200))  # Path to profile picture
    identity_card = db.Column(db.String(200))    # Path to identity card
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    addresses = db.relationship('Address', backref='user', lazy=True)
    cart = db.relationship('CartItem', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)
    wallet = db.relationship('Wallet', backref='user', uselist=False)

    @classmethod
    def generate_username(cls):
        """Generate a unique username in the format 'user#number'"""
        # Get the total number of users
        total_users = cls.query.count()
        # Generate username
        username = f'user{total_users + 1}'
        # Check if username exists
        while cls.query.filter_by(username=username).first():
            total_users += 1
            username = f'user{total_users + 1}'
        return username

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_recent_orders(self, months=2):
        two_months_ago = datetime.utcnow() - timedelta(days=months * 30)
        return Order.query.filter(
            Order.user_id == self.id,
            Order.created_at >= two_months_ago
        ).order_by(Order.created_at.desc()).all()

    @classmethod
    def format_phone_number(cls, phone_number):
        """Format phone number to Iranian format (+98)"""
        # Remove any non-digit characters
        phone_number = ''.join(filter(str.isdigit, phone_number))
        
        # If number starts with 0, replace it with +98
        if phone_number.startswith('0'):
            phone_number = '+98' + phone_number[1:]
        # If number doesn't start with +98 or 98, add +98
        elif not phone_number.startswith('98'):
            phone_number = '+98' + phone_number
        # If number starts with 98 but not +98, add the +
        elif phone_number.startswith('98') and not phone_number.startswith('+98'):
            phone_number = '+' + phone_number
            
        return phone_number

    @classmethod
    def create_default_admin(cls):
        admin = cls.query.filter_by(phone_number='+989137597568').first()
        if not admin:
            admin = cls(
                username='Admin',
                phone_number='+989137597568',
                is_admin=True,
                is_verified=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created successfully!")
        return admin

    @classmethod
    def get_by_phone(cls, phone_number):
        return cls.query.filter_by(phone_number=phone_number).first()

class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    street = db.Column(db.String(200), nullable=False)
    tag = db.Column(db.String(50), nullable=False)
    building_unit_number = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Address {self.tag} - {self.street}>'

class StoreLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<StoreLocation {self.name}>'

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    delivery_fee = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending_approval')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    preparation_start = db.Column(db.DateTime)
    estimated_completion = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancelled_by = db.Column(db.String(20))  # 'user' or 'admin'
    description = db.Column(db.Text)  # New field for order description
    
    # Delivery information
    delivery_type = db.Column(db.String(20), nullable=False)  # 'pickup' or 'delivery'
    store_location_id = db.Column(db.Integer, db.ForeignKey('store_location.id'))
    address_id = db.Column(db.Integer, db.ForeignKey('address.id'))
    
    # Payment information
    payment_method = db.Column(db.String(20), default='cash')  # 'cash' or 'wallet'
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy=True)
    store_location = db.relationship('StoreLocation', backref='orders')
    address = db.relationship('Address', backref='orders')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    
    # Relationship
    product = db.relationship('Product')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50))
    image_url = db.Column(db.String(200))
    discount = db.Column(db.Float, default=0)
    is_featured = db.Column(db.Boolean, default=False)
    is_verified_only = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    product = db.relationship('Product') 

class Wallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    transactions = db.relationship('WalletTransaction', backref='wallet', lazy=True)

class WalletTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallet.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'deposit' or 'withdrawal'
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, wallet_id, amount, type, description=None):
        self.wallet_id = wallet_id
        self.amount = amount
        self.type = type
        self.description = description
        self.created_at = datetime.utcnow()

class OrderComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Rating categories (1-5 stars)
    food_quality = db.Column(db.Integer, nullable=False)  # کیفیت غذا
    delivery_service = db.Column(db.Integer, nullable=False)  # کیفیت سرویس دهی
    packaging = db.Column(db.Integer, nullable=False)  # بسته بندی
    value_for_money = db.Column(db.Integer, nullable=False)  # ارزش به پول
    overall_experience = db.Column(db.Integer, nullable=False)  # تجربه کلی
    
    comment = db.Column(db.Text)  # Optional text comment
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref=db.backref('comment', uselist=False))
    user = db.relationship('User', backref=db.backref('order_comments', lazy=True))

    def get_average_rating(self):
        """Calculate average rating from all categories"""
        ratings = [self.food_quality, self.delivery_service, self.packaging, 
                  self.value_for_money, self.overall_experience]
        return sum(ratings) / len(ratings)

    def __repr__(self):
        return f'<OrderComment {self.id} - Order {self.order_id}>' 