from flask import Flask, render_template, request, redirect, url_for, flash, current_app, jsonify, session
from flask_login import login_user, login_required, logout_user, current_user
from forms import LoginForm, RegisterForm, RegisterAddressForm, ProfileForm, AddressForm, PasswordResetForm
from models import User, Product, CartItem, Address, Order, OrderItem, StoreLocation, Wallet, WalletTransaction, OrderComment
from extensions import db, login_manager, migrate
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import uuid
from sqlalchemy import or_
from flask_wtf.csrf import generate_csrf
from translations import translations
from sqlalchemy.sql import func
import jdatetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///supermarket.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_ADDRESSES'] = 10
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
app.config['SESSION_TYPE'] = 'filesystem'

# Language configuration
app.config['LANGUAGES'] = ['en', 'fa']
app.config['DEFAULT_LANGUAGE'] = 'fa'

# Ensure upload directory exists
os.makedirs(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']), exist_ok=True)

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

def get_language():
    return session.get('language', 'fa')

def get_translation(key):
    """Get translation for the current language"""
    language = session.get('language', 'fa')
    return translations[language].get(key, translations['fa'].get(key, key))

def flash_translated(message_key, category='message'):
    """Flash a translated message"""
    message = get_translation(message_key)
    flash(message, category)

@app.route('/set_language/<language>')
def set_language(language):
    if language in app.config['LANGUAGES']:
        session['language'] = language
    return redirect(request.referrer or url_for('index'))

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf())

@app.context_processor
def inject_translations():
    return dict(
        get_translation=get_translation,
        current_language=get_language()
    )

@app.context_processor
def inject_cart_count():
    if current_user.is_authenticated:
        cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
    else:
        cart_count = 0
    return dict(cart_count=cart_count)

def to_tehran_time(dt):
    if dt is None:
        return None
    # Convert to Tehran timezone
    tehran_dt = dt + timedelta(hours=3, minutes=30)
    # Convert to Shamsi date
    jdate = jdatetime.datetime.fromgregorian(datetime=tehran_dt)
    return jdate

@app.context_processor
def inject_tehran_time():
    return dict(to_tehran_time=to_tehran_time)

# Admin required decorator
def admin_required(f):
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash_translated('access_denied', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    # Get categories from database
    categories = list(set([p.category for p in Product.query.all()]))
    
    # Get featured products (only show verified-only products to verified users)
    featured_products = Product.query.filter_by(is_featured=True)
    if not current_user.is_authenticated or not current_user.is_verified:
        featured_products = featured_products.filter_by(is_verified_only=False)
    featured_products = featured_products.all()
    
    # Get products by category
    products_by_category = {}
    for category in categories:
        products = Product.query.filter_by(category=category)
        if not current_user.is_authenticated or not current_user.is_verified:
            products = products.filter_by(is_verified_only=False)
        products_by_category[category] = products.all()
    
    return render_template('index.html', 
                         categories=categories,
                         featured_products=featured_products,
                         products_by_category=products_by_category)

@app.route('/category/<category>')
def category(category):
    products = Product.query.filter_by(category=category)
    if not current_user.is_authenticated or not current_user.is_verified:
        products = products.filter_by(is_verified_only=False)
    products = products.all()
    return render_template('category.html', products=products, category=category)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get statistics
    total_products = Product.query.count()
    categories = list(set([p.category for p in Product.query.all()]))
    locations = StoreLocation.query.all()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    products = Product.query.all()
    
    # Get delivery settings from session or use defaults
    delivery_fee_percentage = session.get('delivery_fee_percentage', 5.0)
    min_delivery_fee = session.get('min_delivery_fee', 20000)
    
    return render_template('admin/dashboard.html',
                         total_products=total_products,
                         categories=categories,
                         locations=locations,
                         recent_orders=recent_orders,
                         products=products,
                         delivery_fee_percentage=delivery_fee_percentage,
                         min_delivery_fee=min_delivery_fee)

@app.route('/admin/update_delivery_settings', methods=['POST'])
@admin_required
def admin_update_delivery_settings():
    try:
        delivery_fee_percentage = float(request.form.get('delivery_fee_percentage', 5))
        min_delivery_fee = float(request.form.get('min_delivery_fee', 20000))
        
        if delivery_fee_percentage < 0 or delivery_fee_percentage > 100 or min_delivery_fee < 0:
            flash_translated('invalid_delivery_settings', 'error')
            return redirect(url_for('admin_dashboard'))
        
        session['delivery_fee_percentage'] = delivery_fee_percentage
        session['min_delivery_fee'] = min_delivery_fee
        
        flash_translated('delivery_settings_updated', 'success')
    except ValueError:
        flash_translated('invalid_delivery_settings', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash_translated('access_denied', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        stock = int(request.form.get('stock'))
        category = request.form.get('category')
        image_url = request.form.get('image_url')
        discount = float(request.form.get('discount', 0))
        is_featured = 'is_featured' in request.form
        is_verified_only = 'is_verified_only' in request.form
        
        product = Product(
            name=name,
            description=description,
            price=price,
            stock=stock,
            category=category,
            image_url=image_url,
            discount=discount,
            is_featured=is_featured,
            is_verified_only=is_verified_only
        )
        
        db.session.add(product)
        db.session.commit()
        
        flash_translated('item_added', 'success')
        return redirect(url_for('admin_dashboard'))
    
    # Get all categories for the form
    categories = db.session.query(Product.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('admin/add_product.html', categories=categories)

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if not current_user.is_admin:
        flash_translated('access_denied', 'danger')
        return redirect(url_for('index'))
    
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.stock = int(request.form.get('stock'))
        product.category = request.form.get('category')
        product.image_url = request.form.get('image_url')
        product.discount = float(request.form.get('discount', 0))
        product.is_featured = 'is_featured' in request.form
        product.is_verified_only = 'is_verified_only' in request.form
        
        db.session.commit()
        flash_translated('item_updated', 'success')
        return redirect(url_for('admin_dashboard'))
    
    # Get all categories for the form
    categories = db.session.query(Product.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('admin/edit_product.html', product=product, categories=categories)

@app.route('/admin/product/delete/<int:product_id>')
@login_required
def admin_delete_product(product_id):
    if not current_user.is_admin:
        flash_translated('access_denied', 'danger')
        return redirect(url_for('index'))
    
    product = Product.query.get_or_404(product_id)
    
    # Delete associated cart items and order items
    CartItem.query.filter_by(product_id=product_id).delete()
    OrderItem.query.filter_by(product_id=product_id).delete()
    
    db.session.delete(product)
    db.session.commit()
    
    flash_translated('item_deleted', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/category/add', methods=['POST'])
@admin_required
def admin_add_category():
    category_name = request.form.get('category_name')
    if category_name:
        # Check if category already exists
        existing_category = db.session.query(Product.category).filter_by(category=category_name).first()
        if not existing_category:
            # Create a placeholder product to establish the category
            product = Product(
                name=f'Sample {category_name}',
                description=f'Sample product for {category_name} category',
                price=0.0,
                category=category_name,
                stock=0,
                image_url='https://via.placeholder.com/500'
            )
            db.session.add(product)
            db.session.commit()
            flash_translated('category_added')
        else:
            flash_translated('category_exists')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/category/edit/<category>', methods=['GET', 'POST'])
@admin_required
def admin_edit_category(category):
    if request.method == 'POST':
        new_name = request.form.get('category_name')
        if new_name and new_name != category:
            # Update all products in this category
            Product.query.filter_by(category=category).update({'category': new_name})
            db.session.commit()
            flash_translated('category_updated')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/edit_category.html', category=category)

@app.route('/admin/category/delete/<category>')
@admin_required
def admin_delete_category(category):
    # Check if category has any products
    products = Product.query.filter_by(category=category).all()
    if products:
        # Delete all products in this category
        for product in products:
            # Delete related cart items
            CartItem.query.filter_by(product_id=product.id).delete()
            # Delete related order items
            OrderItem.query.filter_by(product_id=product.id).delete()
        # Delete the products
        Product.query.filter_by(category=category).delete()
        db.session.commit()
        flash_translated('category_and_products_deleted')
    else:
        flash_translated('category_not_found_or_already_deleted')
    return redirect(url_for('admin_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    
    # Handle phone number change request
    if request.method == 'POST' and 'change_phone' in request.form:
        session.pop('login_step', None)
        session.pop('login_phone', None)
        return redirect(url_for('login'))
    
    # Get current step from session or default to 1
    current_step = session.get('login_step', 1)
    form.step = current_step

    if form.validate_on_submit():
        if current_step == 1:
            # Step 1: Phone number verification
            formatted_phone = User.format_phone_number(form.phone_number.data)
            user = User.query.filter_by(phone_number=formatted_phone).first()
            
            # If user doesn't exist, create a new user
            if user is None:
                try:
                    # Create new user
                    user = User(
                        username=f"User_{formatted_phone[-4:]}",  # Create username from last 4 digits
                        phone_number=formatted_phone,
                        is_verified=False,
                        email=None,  # Initialize email as None
                        profile_picture=None,  # Initialize profile picture as None
                        identity_card=None,  # Initialize identity card as None
                        is_admin=False  # Initialize is_admin as False
                    )
                    db.session.add(user)
                    db.session.flush()  # Flush to get the user ID
                    
                    # Create wallet for the new user
                    wallet = Wallet(
                        user_id=user.id,
                        balance=0.0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.session.add(wallet)
                    db.session.commit()
                    
                except Exception as e:
                    db.session.rollback()
                    flash_translated('error_creating_user')
                    return redirect(url_for('login'))
            
            # Generate and send verification code
            if user.generate_verification_code():
                flash_translated('verification_code_sent')
                # Store phone and step in session
                session['login_phone'] = formatted_phone
                session['login_step'] = 2
                return redirect(url_for('login'))
            else:
                flash_translated('error_sending_sms')
                return redirect(url_for('login'))
            
        else:
            # Step 2: Verification code check
            formatted_phone = session.get('login_phone')
            if not formatted_phone:
                session['login_step'] = 1
                return redirect(url_for('login'))
                
            user = User.query.filter_by(phone_number=formatted_phone).first()
            if user is None:
                flash_translated('phone_not_found')
                session['login_step'] = 1
                session.pop('login_phone', None)
                return redirect(url_for('login'))
                
            if user.verify_code(form.verification_code.data):
                login_user(user)
                user.clear_verification_code()
                session.pop('login_step', None)
                session.pop('login_phone', None)
                
                # If this is a new user, redirect to profile setup
                if not user.username or user.username.startswith('User_'):
                    return redirect(url_for('profile'))
                
                next_page = request.args.get('next')
                if not next_page or not next_page.startswith('/'):
                    next_page = url_for('index')
                return redirect(next_page)
            else:
                flash_translated('invalid_verification_code')
                session['login_step'] = 2
                return redirect(url_for('login'))

    # For GET requests, maintain the current step
    if current_step == 2:
        form.phone_number.data = session.get('login_phone', '')

    return render_template('login.html', title='Sign In', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username,
            phone_number=form.phone_number.data,
            is_verified=False
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        # Create wallet for the user
        wallet = Wallet(user_id=user.id)
        db.session.add(wallet)
        db.session.commit()
        
        # Log in the user
        login_user(user)
        
        # Redirect to address registration
        return redirect(url_for('register_address'))
    
    return render_template('register.html', form=form)

@app.route('/register/address', methods=['GET', 'POST'])
@login_required
def register_address():
    form = RegisterAddressForm()
    if form.validate_on_submit():
        address = Address(
            user_id=current_user.id,
            street=form.street.data,
            tag=form.tag.data,
            building_unit_number=form.building_unit_number.data,
            description=form.description.data,
            is_default=True  # Set as default address since it's the first one
        )
        db.session.add(address)
        db.session.commit()
        
        flash_translated('address_added', 'success')
        return redirect(url_for('index'))
    
    return render_template('register_address.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    
    # Calculate subtotal with discounts
    subtotal = sum(
        item.product.price * (1 - item.product.discount/100) * item.quantity 
        for item in cart_items
    )
    
    # Get delivery fee settings from session
    delivery_fee_percentage = session.get('delivery_fee_percentage', 5.0)
    min_delivery_fee = session.get('min_delivery_fee', 2.00)
    
    # Calculate delivery fee
    delivery_fee = max(min_delivery_fee, subtotal * (delivery_fee_percentage / 100))
    
    # Calculate total
    total = subtotal + delivery_fee
    
    # Get user's addresses and store locations
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    locations = StoreLocation.query.filter_by(is_active=True).all()
    
    # Ensure user has a wallet
    if not current_user.wallet:
        wallet = Wallet(user_id=current_user.id)
        db.session.add(wallet)
        db.session.commit()
    
    return render_template('cart.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         delivery_fee=delivery_fee,
                         total=total,
                         addresses=addresses,
                         locations=locations)

@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    
    # Verify the cart item belongs to the current user
    if cart_item.user_id != current_user.id:
        flash_translated('unauthorized_action', 'danger')
        return redirect(url_for('cart'))
    
    quantity = int(request.form.get('quantity', 1))
    
    # Validate quantity
    if quantity < 1:
        flash_translated('quantity_must_be_at_least_1', 'danger')
        return redirect(url_for('cart'))
    
    if quantity > cart_item.product.stock:
        flash_translated('only_x_items_available_in_stock', {'x': cart_item.product.stock}, 'danger')
        return redirect(url_for('cart'))
    
    cart_item.quantity = quantity
    db.session.commit()
    
    flash_translated('cart_updated')
    return redirect(url_for('cart'))

@app.route('/add_to_cart/<int:product_id>', methods=['GET', 'POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    
    # Validate quantity
    if quantity < 1:
        flash_translated('quantity_must_be_at_least_1', 'danger')
        return redirect(request.referrer or url_for('index'))
    
    # Check if user has already ordered all available stock
    existing_cart_item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()
    
    if existing_cart_item and existing_cart_item.quantity >= product.stock:
        flash_translated('all_stock_ordered', 'danger')
        return redirect(request.referrer or url_for('index'))
    
    if quantity > product.stock:
        flash_translated('only_x_items_available_in_stock', {'x': product.stock}, 'danger')
        return redirect(request.referrer or url_for('index'))
    
    cart_item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()
    
    if cart_item:
        # Check if adding the new quantity would exceed stock
        if cart_item.quantity + quantity > product.stock:
            flash_translated('only_x_items_available_in_stock', {'x': product.stock}, 'danger')
            return redirect(request.referrer or url_for('index'))
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(user_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    
    db.session.commit()
    flash_translated('product_added_to_cart')
    
    # Return to the previous page or home if no referrer
    return redirect(request.referrer or url_for('index'))

@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    try:
        cart_item = CartItem.query.get_or_404(item_id)
        if cart_item.user_id != current_user.id:
            flash_translated('access_denied', 'error')
            return redirect(url_for('cart'))
        
        db.session.delete(cart_item)
        db.session.commit()
        flash_translated('item_removed_from_cart')
    except Exception as e:
        db.session.rollback()
        flash_translated('error_removing_item_from_cart')
    
    return redirect(url_for('cart'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Get user's orders
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    
    # Get user's order comments
    order_comments = OrderComment.query.filter_by(user_id=current_user.id).order_by(OrderComment.created_at.desc()).all()
    
    form = ProfileForm()
    if form.validate_on_submit():
        if form.profile_picture.data:
            profile_picture_path = save_file(form.profile_picture.data, 'profile_pictures')
            if profile_picture_path:
                current_user.profile_picture = profile_picture_path

        if form.identity_card.data:
            identity_card_path = save_file(form.identity_card.data, 'identity_cards')
            if identity_card_path:
                current_user.identity_card = identity_card_path
                current_user.is_verified = False  # Reset verification when new ID is uploaded

        current_user.username = form.username.data
        current_user.phone_number = form.phone_number.data
        
        # Only update email if it's provided and not empty
        if form.email.data and form.email.data.strip():
            current_user.email = form.email.data
        else:
            current_user.email = None
        
        db.session.commit()
        flash_translated('profile_updated')
        return redirect(url_for('profile'))

    # Pre-fill form with current user data
    if request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.phone_number.data = current_user.phone_number

    # Get recent orders and addresses
    recent_orders = current_user.get_recent_orders(months=2)
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    
    # Get the order_id from the URL parameters if it exists
    order_id = request.args.get('order_id')
    
    return render_template('profile.html', 
                         form=form, 
                         user=current_user,
                         recent_orders=recent_orders,
                         addresses=addresses,
                         highlighted_order_id=order_id,
                         orders=orders,
                         order_comments=order_comments)

@app.route('/address/add', methods=['GET', 'POST'])
@login_required
def add_address():
    # Check if user has reached the maximum number of addresses
    if Address.query.filter_by(user_id=current_user.id).count() >= app.config['MAX_ADDRESSES']:
        flash_translated('reached_max_addresses', 'error')
        return redirect(url_for('profile'))

    form = AddressForm()
    if form.validate_on_submit():
        try:
            # Create new address
            address = Address(
                user_id=current_user.id,
                street=form.street.data,
                tag=form.tag.data,
                building_unit_number=form.building_unit_number.data,
                description=form.description.data,
                is_default=form.is_default.data
            )
            
            # If this is set as default, update other addresses
            if form.is_default.data:
                Address.query.filter_by(user_id=current_user.id).update({'is_default': False})
            
            db.session.add(address)
            db.session.commit()
            
            flash_translated('address_added')
            return redirect(url_for('profile'))
        except Exception as e:
            db.session.rollback()
            flash_translated('error_adding_address', 'error')
            return redirect(url_for('add_address'))
    
    return render_template('address_form.html', form=form)

@app.route('/address/edit/<int:address_id>', methods=['GET', 'POST'])
@login_required
def edit_address(address_id):
    address = Address.query.get_or_404(address_id)
    if address.user_id != current_user.id:
        flash_translated('no_permission_to_edit_address')
        return redirect(url_for('profile'))

    form = AddressForm(obj=address)
    if form.validate_on_submit():
        address.street = form.street.data
        address.tag = form.tag.data
        address.building_unit_number = form.building_unit_number.data
        address.description = form.description.data
        
        if form.is_default.data and not address.is_default:
            # Set all other addresses as non-default
            Address.query.filter_by(user_id=current_user.id).update({'is_default': False})
        address.is_default = form.is_default.data
        
        db.session.commit()
        flash_translated('address_updated')
        return redirect(url_for('profile'))
    
    return render_template('address_form.html', form=form, address=address)

@app.route('/address/delete/<int:address_id>')
@login_required
def delete_address(address_id):
    address = Address.query.get_or_404(address_id)
    if address.user_id != current_user.id:
        flash_translated('no_permission_to_delete_address')
        return redirect(url_for('profile'))

    db.session.delete(address)
    db.session.commit()
    flash_translated('address_deleted')
    return redirect(url_for('profile'))

@app.route('/admin/verify_user/<int:user_id>')
@admin_required
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    db.session.commit()
    flash_translated('user_verified', {'username': user.username})
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.filter(User.identity_card.isnot(None), 
                            User.is_verified.is_(False)).all()
    return render_template('admin/users.html', users=users)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if query:
        products = Product.query.filter(
            or_(
                Product.name.ilike(f'%{query}%'),
                Product.description.ilike(f'%{query}%'),
                Product.category.ilike(f'%{query}%')
            )
        ).all()
    else:
        products = []
    return render_template('search_results.html', products=products, query=query)

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    
    if not cart_items:
        flash_translated('cart_empty', 'error')
        return redirect(url_for('cart'))
    
    # Calculate subtotal
    subtotal = sum(item.product.price * item.quantity * (1 - item.product.discount/100) 
                  for item in cart_items)
    
    if request.method == 'POST':
        delivery_type = request.form.get('delivery_type')
        delivery_fee = 0.0  # Default delivery fee
        
        if delivery_type == 'pickup':
            store_location_id = request.form.get('store_location_id')
            if not store_location_id:
                flash_translated('please_select_store_location', 'error')
                return redirect(url_for('cart'))
            store_location = StoreLocation.query.get_or_404(store_location_id)
            delivery_fee = 0.0  # Ensure pickup orders have no delivery fee
        else:  # delivery
            address_id = request.form.get('delivery_address_id')
            if not address_id:
                flash_translated('please_select_delivery_address', 'error')
                return redirect(url_for('cart'))
            address = Address.query.get_or_404(address_id)
            # Calculate delivery fee (5% of subtotal with 20000 Tooman minimum)
            delivery_fee = max(20000, subtotal * 0.05)
        
        # Calculate total with delivery fee
        total = subtotal + delivery_fee
        
        # Get payment method
        payment_method = request.form.get('payment_method', 'cash')
        
        # If payment method is online, redirect to payment temp page
        if payment_method == 'online':
            # Store order details in session for payment success
            session['order_total'] = total
            session['payment_method'] = payment_method
            session['delivery_type'] = delivery_type
            session['store_location_id'] = store_location_id if delivery_type == 'pickup' else None
            session['address_id'] = address_id if delivery_type == 'delivery' else None
            session['order_description'] = request.form.get('order_description', '').strip()  # Store order description in session
            
            # Redirect to payment temp page
            return redirect(url_for('payment_temp', amount=total, type='order'))
        
        # If payment method is wallet, check balance
        if payment_method == 'wallet':
            if not current_user.wallet:
                wallet = Wallet(user_id=current_user.id, balance=0.0)
                db.session.add(wallet)
            else:
                wallet = current_user.wallet
                if wallet.balance is None:
                    wallet.balance = 0.0
            
            # Calculate remaining amount to be paid
            remaining_amount = total - wallet.balance
            
            if remaining_amount > 0:
                # Store order details in session for payment success
                session['order_total'] = total
                session['wallet_amount'] = wallet.balance
                session['remaining_amount'] = remaining_amount
                session['payment_method'] = payment_method
                session['delivery_type'] = delivery_type
                session['store_location_id'] = store_location_id if delivery_type == 'pickup' else None
                session['address_id'] = address_id if delivery_type == 'delivery' else None
                session['order_description'] = request.form.get('order_description', '').strip()  # Store order description directly from form
                
                # Redirect to payment temp page with the remaining amount
                return redirect(url_for('payment_temp', amount=remaining_amount, type='order'))
            
            # If wallet balance is sufficient, create order directly
            order = Order(
                user_id=current_user.id,
                total_amount=total,
                delivery_fee=delivery_fee,
                status='pending_approval',
                payment_method=payment_method,
                delivery_type=delivery_type,
                store_location_id=store_location_id if delivery_type == 'pickup' else None,
                address_id=address_id if delivery_type == 'delivery' else None,
                description=request.form.get('order_description', '').strip()  # Get order description directly from form
            )
            db.session.add(order)
            
            # Create order items
            for cart_item in cart_items:
                order_item = OrderItem(
                    order=order,
                    product_id=cart_item.product_id,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price * (1 - cart_item.product.discount/100)
                )
                db.session.add(order_item)
            
            # Clear cart
            for cart_item in cart_items:
                db.session.delete(cart_item)
            
            # Update wallet balance
            wallet.balance -= total
            
            # Create wallet transaction
            transaction = WalletTransaction(
                wallet_id=wallet.id,
                amount=total,
                type='withdrawal',
                description=get_translation('order_payment')
            )
            db.session.add(transaction)
            
            db.session.commit()
            
            flash_translated('order_placed_successfully', 'success')
            return redirect(url_for('order_status', order_id=order.id))
        
        # For cash payment, create order directly
        order = Order(
            user_id=current_user.id,
            total_amount=total,
            delivery_fee=delivery_fee,
            status='pending_approval',
            payment_method=payment_method,
            delivery_type=delivery_type,
            store_location_id=store_location_id if delivery_type == 'pickup' else None,
            address_id=address_id if delivery_type == 'delivery' else None,
            description=request.form.get('order_description', '').strip()  # Get order description directly from form
        )
        db.session.add(order)
        
        # Create order items
        for cart_item in cart_items:
            order_item = OrderItem(
                order=order,
                product_id=cart_item.product_id,
                quantity=cart_item.quantity,
                price=cart_item.product.price * (1 - cart_item.product.discount/100)
            )
            db.session.add(order_item)
        
        # Clear cart
        for cart_item in cart_items:
            db.session.delete(cart_item)
        
        db.session.commit()
        
        flash_translated('order_placed_successfully', 'success')
        return redirect(url_for('order_status', order_id=order.id))
    
    # For GET request, calculate delivery fee for display
    delivery_fee = max(20000, subtotal * 0.05)  # Default to delivery fee
    total = subtotal + delivery_fee
    
    # Get user's addresses and store locations
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    locations = StoreLocation.query.filter_by(is_active=True).all()
    
    return render_template('cart.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         delivery_fee=delivery_fee,
                         total=total,
                         addresses=addresses,
                         locations=locations)

@app.route('/orders')
@login_required
def orders():
    # View all orders
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)

@app.route('/order/<int:order_id>', methods=['GET'])
@login_required
def order_status(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    # Ensure the comment is included in the order object
    return render_template('order_status.html', order=order)

@app.route('/admin/orders')
@admin_required
def admin_orders():
    # Get orders that need approval
    pending_orders = Order.query.filter_by(status='pending_approval').order_by(Order.created_at.desc()).all()
    # Get orders that are being prepared
    preparing_orders = Order.query.filter_by(status='preparing').order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', 
                         pending_orders=pending_orders,
                         preparing_orders=preparing_orders)

@app.route('/admin/order/<int:order_id>/approve', methods=['POST'])
@admin_required
def approve_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status != 'pending_approval':
        flash_translated('this_order_has_already_been_processed')
        return redirect(url_for('admin_orders'))
    
    # Check stock availability
    for item in order.items:
        if item.product.stock < item.quantity:
            flash_translated('not_enough_stock', {'product_name': item.product.name})
            return redirect(url_for('admin_orders'))
        
        # Reduce stock
        item.product.stock -= item.quantity
    
    # Handle wallet payment if the order was paid with wallet
    if order.payment_method == 'wallet':
        user_wallet = order.user.wallet
        if not user_wallet or user_wallet.balance < order.total_amount:
            flash_translated('insufficient_wallet_balance', 'error')
            return redirect(url_for('admin_orders'))
        
        # Create withdrawal transaction
        transaction = WalletTransaction(
            wallet_id=user_wallet.id,
            amount=order.total_amount,
            type='withdrawal',
            description=get_translation('order_payment')
        )
        db.session.add(transaction)
        
        # Update wallet balance
        user_wallet.balance -= order.total_amount
    
    order.status = 'preparing'
    order.preparation_start = datetime.utcnow()
    order.estimated_completion = datetime.utcnow() + timedelta(minutes=45)
    db.session.commit()
    
    flash_translated('order_approved_and_moved_to_preparation')
    return redirect(url_for('admin_orders'))

@app.route('/admin/order/<int:order_id>/complete', methods=['POST'])
@admin_required
def complete_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status != 'preparing':
        flash_translated('this_order_is_not_in_preparation')
        return redirect(url_for('admin_orders'))
    
    order.status = 'completed'
    order.completed_at = datetime.utcnow()
    db.session.commit()
    
    flash_translated('order_marked_as_completed')
    return redirect(url_for('admin_orders'))

@app.route('/admin/order/<int:order_id>/reject', methods=['POST'])
@admin_required
def reject_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status != 'pending_approval':
        flash_translated('this_order_cannot_be_rejected_anymore')
        return redirect(url_for('admin_orders'))
    
    order.status = 'rejected'
    db.session.commit()
    
    flash_translated('order_has_been_rejected')
    return redirect(url_for('admin_orders'))

@app.route('/api/auto_complete_order/<int:order_id>', methods=['POST'])
@login_required
def auto_complete_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == 'preparing' and datetime.utcnow() >= order.estimated_completion:
        order.status = 'completed'
        order.completed_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Order auto-completed'})
    return jsonify({'status': 'error', 'message': 'Order cannot be auto-completed'}), 400

@app.route('/admin/locations')
@admin_required
def admin_locations():
    locations = StoreLocation.query.all()
    return render_template('admin/locations.html', locations=locations)

@app.route('/admin/location/add', methods=['GET', 'POST'])
@admin_required
def admin_add_location():
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        description = request.form.get('description')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        is_active = 'is_active' in request.form
        
        location = StoreLocation(
            name=name,
            address=address,
            description=description,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            is_active=is_active
        )
        
        db.session.add(location)
        db.session.commit()
        
        flash_translated('location_added')
        return redirect(url_for('admin_locations'))
    
    return render_template('admin/add_location.html')

@app.route('/admin/location/edit/<int:location_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_location(location_id):
    location = StoreLocation.query.get_or_404(location_id)
    
    if request.method == 'POST':
        location.name = request.form.get('name')
        location.address = request.form.get('address')
        location.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash_translated('location_updated')
        return redirect(url_for('admin_locations'))
    
    return render_template('admin/edit_location.html', location=location)

@app.route('/admin/location/delete/<int:location_id>', methods=['POST'])
@admin_required
def admin_delete_location(location_id):
    try:
        location = StoreLocation.query.get_or_404(location_id)
        
        # Check if location has any orders
        if Order.query.filter_by(store_location_id=location_id).first():
            flash_translated('cannot_delete_location_with_associated_orders')
            return redirect(url_for('admin_locations'))
        
        # Delete the location
        db.session.delete(location)
        db.session.commit()
        
        flash_translated('location_deleted')
    except Exception as e:
        db.session.rollback()
        flash_translated('error_deleting_location', 'error')
        print(f"Error deleting location: {str(e)}")
    
    return redirect(url_for('admin_locations'))

@app.route('/admin/update_category_icon/<category>', methods=['POST'])
@admin_required
def admin_update_category_icon(category):
    icon = request.form.get('icon')
    if icon:
        category_icons = session.get('category_icons', {})
        category_icons[category] = icon
        session['category_icons'] = category_icons
        flash_translated('category_icon_updated')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/<int:order_id>')
@admin_required
def admin_order_details(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/order_details.html', order=order)

@app.route('/reset_password', methods=['GET', 'POST'])
@login_required
def reset_password():
    form = PasswordResetForm()
    if form.validate_on_submit():
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash_translated('password_updated')
        return redirect(url_for('profile'))
    return render_template('reset_password.html', form=form)

@app.cli.command("create-admin")
def create_admin():
    """Create the admin user if it doesn't exist"""
    admin = User.query.filter_by(phone_number='+989137597568').first()
    if not admin:
        admin = User(
            username='Admin',
            phone_number='+989137597568',
            is_admin=True,
            is_verified=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")
    else:
        print("Admin user already exists!")

@app.cli.command("reset-admin-password")
def reset_admin_password():
    """Reset the admin user's password"""
    admin = User.query.filter_by(phone_number='+989137597568').first()
    if admin:
        admin.set_password('admin123')
        db.session.commit()
        print("Admin password reset successfully!")
    else:
        print("Admin user not found!")

@app.cli.command("create-sample-products")
def create_sample_products():
    """Delete existing products and create new sample products in Farsi"""
    # Delete all existing products
    Product.query.delete()
    
    # Sample products in Farsi with prices in Tooman
    products = [
        # میوه‌ها و سبزیجات
        {
            "name": "سیب قرمز",
            "description": "سیب قرمز تازه و آبدار",
            "price": 45000,
            "stock": 100,
            "category": "میوه‌ها و سبزیجات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/a/a6/Pink_lady_and_cross_section.jpg",
            "discount": 0
        },
        {
            "name": "موز",
            "description": "موز تازه و رسیده",
            "price": 35000,
            "stock": 150,
            "category": "میوه‌ها و سبزیجات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/8/8a/Banana-Single.jpg",
            "discount": 5
        },
        {
            "name": "گوجه فرنگی",
            "description": "گوجه فرنگی تازه و محلی",
            "price": 25000,
            "stock": 200,
            "category": "میوه‌ها و سبزیجات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/8/89/Tomato_je.jpg",
            "discount": 0
        },
        
        # لبنیات و تخم مرغ
        {
            "name": "شیر تازه",
            "description": "شیر تازه محلی",
            "price": 55000,
            "stock": 50,
            "category": "لبنیات و تخم مرغ",
            "image_url": "https://www.bing.com/ck/a?!&&p=9d2af53238cce7c3917b6031d2617513bc92b1ac3db52c27c4eba784da5a57edJmltdHM9MTc0MzQ2NTYwMA&ptn=3&ver=2&hsh=4&fclid=285537f9-21ba-633e-14d9-23a0202362c7&u=a1L2ltYWdlcy9zZWFyY2g_cT0lZDglYjQlZGIlOGMlZDglYjErJWQ5JTg0JWQ4JWE4JWQ5JTg2JWRiJThjJWQ4JWE3JWQ4JWFhJmlkPTNCQzEzNEVFM0Q3OUQ5REU4RkUyQkU4Qzk1RUI3OTEwNzcwMUFFRjgmRk9STT1JUUZSQkE&ntb=1",
            "discount": 0
        },
        {
            "name": "پنیر محلی",
            "description": "پنیر محلی تازه",
            "price": 85000,
            "stock": 30,
            "category": "لبنیات و تخم مرغ",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/2/2c/White_cheese.jpg",
            "discount": 10
        },
        {
            "name": "تخم مرغ محلی",
            "description": "تخم مرغ تازه محلی",
            "price": 45000,
            "stock": 100,
            "category": "لبنیات و تخم مرغ",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/5/5f/White_eggs.jpg",
            "discount": 0
        },
        
        # نان و شیرینی
        {
            "name": "نان تازه",
            "description": "نان تازه محلی",
            "price": 15000,
            "stock": 200,
            "category": "نان و شیرینی",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/33/Fresh_made_whole_meal_bread_loaves.jpg",
            "discount": 0
        },
        {
            "name": "کیک شکلاتی",
            "description": "کیک شکلاتی تازه",
            "price": 95000,
            "stock": 20,
            "category": "نان و شیرینی",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/0/04/Pound_layer_cake.jpg",
            "discount": 15
        },
        
        # گوشت و مرغ
        {
            "name": "گوشت گوسفندی",
            "description": "گوشت تازه گوسفندی",
            "price": 450000,
            "stock": 30,
            "category": "گوشت و مرغ",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Lamb_cuts.svg",
            "discount": 0
        },
        {
            "name": "مرغ تازه",
            "description": "مرغ تازه محلی",
            "price": 150000,
            "stock": 40,
            "category": "گوشت و مرغ",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/5/5f/Chicken_meat.jpg",
            "discount": 5
        },
        
        # برنج و حبوبات
        {
            "name": "برنج ایرانی",
            "description": "برنج ایرانی با کیفیت عالی",
            "price": 250000,
            "stock": 50,
            "category": "برنج و حبوبات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/7/7b/White-rice-cooked.jpg",
            "discount": 0
        },
        {
            "name": "عدس",
            "description": "عدس تازه و تمیز",
            "price": 85000,
            "stock": 100,
            "category": "برنج و حبوبات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/7/70/Red_Lentil.JPG",
            "discount": 10
        },
        
        # روغن و چاشنی
        {
            "name": "روغن زیتون",
            "description": "روغن زیتون اصل",
            "price": 350000,
            "stock": 40,
            "category": "روغن و چاشنی",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/4/4c/Olive_oil.jpg",
            "discount": 0
        },
        {
            "name": "زعفران",
            "description": "زعفران اصل قائنات",
            "price": 950000,
            "stock": 20,
            "category": "روغن و چاشنی",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/4/4c/Saffron_threads.jpg",
            "discount": 0
        },
        
        # نوشیدنی‌ها
        {
            "name": "دوغ محلی",
            "description": "دوغ محلی تازه",
            "price": 25000,
            "stock": 100,
            "category": "نوشیدنی‌ها",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Doogh.jpg",
            "discount": 0
        },
        {
            "name": "شربت زعفران",
            "description": "شربت زعفران خانگی",
            "price": 45000,
            "stock": 50,
            "category": "نوشیدنی‌ها",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/4/4c/Saffron_syrup.jpg",
            "discount": 5
        },
        
        # تنقلات
        {
            "name": "پسته",
            "description": "پسته تازه رفسنجان",
            "price": 450000,
            "stock": 30,
            "category": "تنقلات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Pistachios.jpg",
            "discount": 0
        },
        {
            "name": "بادام",
            "description": "بادام تازه محلی",
            "price": 350000,
            "stock": 40,
            "category": "تنقلات",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Almonds.jpg",
            "discount": 10
        },
        
        # مواد شوینده
        {
            "name": "مایع ظرفشویی",
            "description": "مایع ظرفشویی با کیفیت",
            "price": 45000,
            "stock": 100,
            "category": "مواد شوینده",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Dishwashing_liquid.jpg",
            "discount": 0
        },
        {
            "name": "پودر لباسشویی",
            "description": "پودر لباسشویی با کیفیت",
            "price": 85000,
            "stock": 50,
            "category": "مواد شوینده",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Laundry_detergent.jpg",
            "discount": 5
        },
        
        # لوازم بهداشتی
        {
            "name": "صابون گلیسیرینه",
            "description": "صابون گلیسیرینه مراقبت پوست",
            "price": 35000,
            "stock": 100,
            "category": "لوازم بهداشتی",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Glycerin_soap.jpg",
            "discount": 0
        },
        {
            "name": "خمیر دندان",
            "description": "خمیر دندان با کیفیت",
            "price": 45000,
            "stock": 80,
            "category": "لوازم بهداشتی",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Toothpaste.jpg",
            "discount": 0
        }
    ]
    
    # Add products to database
    for product_data in products:
        product = Product(**product_data)
        db.session.add(product)
    
    db.session.commit()
    print("Sample products created successfully!")

def init_db():
    """Initialize the database"""
    with app.app_context():
        db.create_all()
        # Create admin user
        admin = User.query.filter_by(phone_number='+989137597568').first()
        if not admin:
            admin = User(
                username='Admin',
                phone_number='+989137597568',
                is_admin=True,
                is_verified=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")

@app.route('/wallet')
@login_required
def wallet():
    # Get or create wallet for user
    if not current_user.wallet:
        wallet = Wallet(user_id=current_user.id)
        db.session.add(wallet)
        db.session.commit()
    else:
        wallet = current_user.wallet
    
    # Get transaction history
    transactions = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(WalletTransaction.created_at.desc()).all()
    
    return render_template('wallet.html', wallet=wallet, transactions=transactions)

@app.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Check if order belongs to user
    if order.user_id != current_user.id:
        flash(get_translation('access_denied'), 'error')
        return redirect(url_for('profile'))
    
    # Check if order can be cancelled
    if order.status not in ['pending_approval', 'preparing']:
        flash(get_translation('order_cannot_be_cancelled'), 'error')
        return redirect(url_for('order_status', order_id=order_id))
    
    # Update order status
    order.status = 'cancelled'
    order.cancelled_by = 'user'
    order.cancelled_at = datetime.utcnow()
    
    # Add refund to wallet
    if not current_user.wallet:
        wallet = Wallet(user_id=current_user.id)
        db.session.add(wallet)
    else:
        wallet = current_user.wallet
    
    # Create refund transaction
    transaction = WalletTransaction(
        wallet_id=wallet.id,
        amount=order.total_amount,
        type='deposit',
        description=get_translation('order_cancelled_refund')
    )
    db.session.add(transaction)
    
    # Update wallet balance
    wallet.balance += order.total_amount
    
    db.session.commit()
    flash(get_translation('order_cancelled'), 'success')
    return redirect(url_for('order_status', order_id=order_id))

@app.route('/admin/order/<int:order_id>/cancel', methods=['POST'])
@admin_required
def admin_cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Check if order can be cancelled
    if order.status not in ['pending_approval', 'preparing']:
        flash(get_translation('order_cannot_be_cancelled'), 'error')
        return redirect(url_for('admin_order_details', order_id=order_id))
    
    # Update order status
    order.status = 'cancelled'
    order.cancelled_by = 'admin'
    order.cancelled_at = datetime.utcnow()
    
    # Add refund to user's wallet
    if not order.user.wallet:
        wallet = Wallet(user_id=order.user_id)
        db.session.add(wallet)
    else:
        wallet = order.user.wallet
    
    # Create refund transaction
    transaction = WalletTransaction(
        wallet_id=wallet.id,
        amount=order.total_amount,
        type='deposit',
        description=get_translation('order_cancelled_refund')
    )
    db.session.add(transaction)
    
    # Update wallet balance
    wallet.balance += order.total_amount
    
    db.session.commit()
    flash(get_translation('order_cancelled'), 'success')
    return redirect(url_for('admin_order_details', order_id=order_id))

@app.route('/product/<int:product_id>')
def product_details(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Check if user can access verified-only product
    if product.is_verified_only and (not current_user.is_authenticated or not current_user.is_verified):
        flash(get_translation('login_to_view_verified_product'), 'warning')
        return redirect(url_for('login'))
    
    return render_template('product_details.html', product=product)

def save_file(file, folder):
    """Save an uploaded file securely"""
    if file and file.filename:
        # Get file extension
        filename = secure_filename(file.filename)
        # Create unique filename
        unique_filename = f"{uuid.uuid4()}_{filename}"
        # Create folder path
        folder_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], folder)
        # Ensure folder exists
        os.makedirs(folder_path, exist_ok=True)
        # Full file path
        file_path = os.path.join(folder_path, unique_filename)
        # Save file
        file.save(file_path)
        # Return relative path for database
        return os.path.join('uploads', folder, unique_filename)
    return None

@app.route('/admin/identity-cards')
@login_required
@admin_required
def admin_identity_cards():
    # Get query parameters for filtering and sorting
    verification_status = request.args.get('verification_status', 'all')
    sort_by = request.args.get('sort_by', 'newest')
    search = request.args.get('search', '').lower()

    # Base query for users with identity cards
    query = User.query.filter(User.identity_card.isnot(None))

    # Apply verification filter
    if verification_status == 'verified':
        query = query.filter(User.is_verified == True)
    elif verification_status == 'unverified':
        query = query.filter(User.is_verified == False)

    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )

    # Apply sorting
    if sort_by == 'newest':
        query = query.order_by(User.created_at.desc())
    elif sort_by == 'oldest':
        query = query.order_by(User.created_at.asc())
    elif sort_by == 'username':
        query = query.order_by(User.username.asc())

    # Get the filtered and sorted users
    users = query.all()

    return render_template('admin/identity_cards.html', users=users)

@app.route('/order/<int:order_id>/comment', methods=['GET', 'POST'])
@login_required
def order_comment(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Check if order belongs to user
    if order.user_id != current_user.id:
        flash(get_translation('unauthorized_access'), 'error')
        return redirect(url_for('orders'))
    
    # Allow commenting on completed or rejected orders
    if order.status not in ['completed', 'rejected']:
        flash(get_translation('can_only_rate_completed_orders'), 'error')
        return redirect(url_for('orders'))
    
    # Check if user has already commented
    existing_comment = OrderComment.query.filter_by(order_id=order.id, user_id=current_user.id).first()
    if existing_comment:
        flash(get_translation('already_rated_order'), 'error')
        return redirect(url_for('orders'))
    
    if request.method == 'POST':
        try:
            # Create new comment with correct field mapping
            comment = OrderComment(
                order_id=order.id,
                user_id=current_user.id,
                overall_experience=request.form.get('overall_experience', type=int),
                value_for_money=request.form.get('value_for_money', type=int),
                packaging=request.form.get('packaging', type=int),
                delivery_service=request.form.get('delivery_service', type=int),
                food_quality=request.form.get('food_quality', type=int),
                comment=request.form.get('comment')
            )
            
            db.session.add(comment)
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success'})
            
            flash(get_translation('rating_submitted_successfully'), 'success')
            return redirect(url_for('orders'))
            
        except Exception as e:
            db.session.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': str(e)}), 400
            
            flash(get_translation('error_submitting_rating'), 'error')
            return redirect(url_for('order_status', order_id=order.id))
    
    return redirect(url_for('order_status', order_id=order.id))

@app.route('/admin/order-comments')
@admin_required
def admin_order_comments():
    # Get date filter from query parameters
    selected_date = request.args.get('date')
    
    if selected_date:
        # Convert Shamsi date to Gregorian
        try:
            year, month, day = map(int, selected_date.split('-'))
            shamsi_date = jdatetime.date(year, month, day)
            filter_date = shamsi_date.togregorian()
        except ValueError:
            # If date is invalid, use today's date
            filter_date = datetime.now().date()
    else:
        # If no date provided, use today's date
        filter_date = datetime.now().date()
    
    # Get completed and rejected orders for the selected date
    completed_orders = Order.query.filter(
        Order.status.in_(['completed', 'rejected']),
        func.date(Order.completed_at) == filter_date
    ).order_by(Order.completed_at.desc()).all()
    
    # Get comments for the selected date
    comments = OrderComment.query.join(Order).filter(
        Order.status.in_(['completed', 'rejected']),
        func.date(OrderComment.created_at) == filter_date
    ).order_by(OrderComment.created_at.desc()).all()
    
    # Create a set of order IDs that have comments
    commented_order_ids = {comment.order_id for comment in comments}
    
    # Create entries list with both comments and waiting entries
    entries = []
    
    # Add actual comments first
    for comment in comments:
        comment.is_waiting = False  # Explicitly set is_waiting to False for actual comments
        entries.append(comment)
    
    # Add "Waiting For User Comment" entries for completed/rejected orders without comments
    for order in completed_orders:
        if order.id not in commented_order_ids:
            # Create a custom object for waiting comments
            waiting_comment = type('WaitingComment', (), {
                'order': order,
                'created_at': order.completed_at or order.rejected_at,  # Use completed_at or rejected_at
                'is_waiting': True,
                'food_quality': '-',
                'delivery_service': '-',
                'packaging': '-',
                'value_for_money': '-',
                'overall_experience': '-',
                'comment': None
            })
            entries.append(waiting_comment)
    
    # Sort entries by created_at in descending order
    entries.sort(key=lambda x: x.created_at, reverse=True)
    
    # Convert filter_date back to Shamsi for display
    shamsi_display_date = jdatetime.date.fromgregorian(date=filter_date)
    selected_date = shamsi_display_date.strftime('%Y-%m-%d')
    
    return render_template('admin/order_comments.html', entries=entries, selected_date=selected_date)

@app.route('/api/order/<int:order_id>/status')
@login_required
def get_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Ensure user can only view their own orders
    if order.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'status': order.status,
        'preparation_start': order.preparation_start.strftime('%Y-%m-%d %H:%M') if order.preparation_start else None,
        'estimated_completion': order.estimated_completion.strftime('%Y-%m-%d %H:%M') if order.estimated_completion else None,
        'completed_at': order.completed_at.strftime('%Y-%m-%d %H:%M') if order.completed_at else None
    })

@app.route('/payment_temp')
@login_required
def payment_temp():
    payment_type = request.args.get('type', 'order')
    amount = request.args.get('amount', type=float)
    
    if not amount or amount < 1000:
        flash_translated('invalid_amount', 'error')
        return redirect(url_for('wallet' if payment_type == 'wallet' else 'cart'))
    
    # Store the amount in session for payment success
    session['payment_amount'] = amount
    session['payment_type'] = payment_type
    
    return render_template('payment_temp.html',
                         payment_type=payment_type,
                         amount=amount,
                         success_url=url_for('payment_success', type=payment_type, amount=amount),
                         failure_url=url_for('payment_failure', type=payment_type, amount=amount))

@app.route('/payment_success')
@login_required
def payment_success():
    try:
        payment_type = request.args.get('type', 'order')
        amount = request.args.get('amount', type=float)
        
        if payment_type == 'wallet':
            # Get or create wallet
            if not current_user.wallet:
                wallet = Wallet(user_id=current_user.id, balance=0.0)
                db.session.add(wallet)
            else:
                wallet = current_user.wallet
                if wallet.balance is None:
                    wallet.balance = 0.0
            
            # Create deposit transaction
            transaction = WalletTransaction(
                wallet_id=wallet.id,
                amount=amount,
                type='deposit',
                description=get_translation('wallet_deposit')
            )
            db.session.add(transaction)
            
            # Update wallet balance
            current_balance = float(wallet.balance or 0.0)
            wallet.balance = current_balance + amount
            db.session.commit()
            
            flash_translated('wallet_deposit_successful', 'success')
            return redirect(url_for('wallet'))
        else:
            # Handle order payment
            # Get order details from session
            order_total = session.get('order_total')
            payment_method = session.get('payment_method')
            delivery_type = session.get('delivery_type')
            store_location_id = session.get('store_location_id')
            address_id = session.get('address_id')
            
            if not all([order_total, payment_method, delivery_type]):
                flash_translated('order_details_not_found', 'error')
                return redirect(url_for('cart'))
            
            # Get cart items
            cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
            
            if not cart_items:
                flash_translated('cart_empty', 'error')
                return redirect(url_for('cart'))
            
            # Create order
            order = Order(
                user_id=current_user.id,
                total_amount=order_total,
                delivery_fee=0.0 if delivery_type == 'pickup' else max(20000, order_total * 0.05),
                status='pending_approval',
                payment_method=payment_method,
                delivery_type=delivery_type,
                store_location_id=store_location_id if delivery_type == 'pickup' else None,
                address_id=address_id if delivery_type == 'delivery' else None,
                description=session.get('order_description', '').strip()  # Get order description from session
            )
            db.session.add(order)
            
            # Create order items
            for cart_item in cart_items:
                order_item = OrderItem(
                    order=order,
                    product_id=cart_item.product_id,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price * (1 - cart_item.product.discount/100)
                )
                db.session.add(order_item)
            
            # Clear cart
            for cart_item in cart_items:
                db.session.delete(cart_item)
            
            # Clear session data
            session.pop('order_total', None)
            session.pop('payment_method', None)
            session.pop('delivery_type', None)
            session.pop('store_location_id', None)
            session.pop('address_id', None)
            session.pop('order_description', None)  # Clear order description from session
            
            db.session.commit()
            
            flash_translated('order_payment_successful', 'success')
            return redirect(url_for('admin_orders'))  # Redirect to admin orders page
    except Exception as e:
        db.session.rollback()
        print(f"Error processing payment: {str(e)}")
        flash_translated('error_processing_payment', 'error')
        return redirect(url_for('wallet' if payment_type == 'wallet' else 'cart'))
    
    return redirect(url_for('index'))

@app.route('/payment_failure')
@login_required
def payment_failure():
    payment_type = request.args.get('type', 'order')
    order_id = request.args.get('order_id', type=int)
    amount = request.args.get('amount', type=float)
    
    if payment_type == 'wallet':
        flash_translated('wallet_deposit_failed', 'error')
        return redirect(url_for('wallet'))
    else:
        flash_translated('order_payment_failed', 'error')
        return redirect(url_for('cart'))

@app.route('/process_wallet_deposit', methods=['POST'])
@login_required
def process_wallet_deposit():
    try:
        amount = request.form.get('amount', type=float)
        
        if not amount or amount < 1000:
            flash_translated('invalid_amount', 'error')
            return redirect(url_for('wallet'))
        
        # Store the amount in session for payment success
        session['payment_amount'] = amount
        session['payment_type'] = 'wallet'
        
        # Redirect to payment temp page with the deposit amount
        return redirect(url_for('payment_temp', amount=amount, type='wallet'))
    except Exception as e:
        print(f"Error processing wallet deposit: {str(e)}")
        flash_translated('error_processing_wallet_deposit', 'error')
        return redirect(url_for('wallet'))

if __name__ == '__main__':
    with app.app_context():
        init_db()  # Initialize the database with sample data
    app.run(debug=True, port=8080, host='0.0.0.0') 