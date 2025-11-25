from flask import Flask, render_template, request, redirect, url_for, flash, current_app, jsonify, session
from flask_login import login_user, login_required, logout_user, current_user
from forms import LoginForm, RegisterForm, RegisterAddressForm, ProfileForm, AddressForm
from models import User, Product, CartItem, Address, Order, OrderItem, StoreLocation, OrderComment, Brand, Category
from extensions import db, login_manager, migrate
import os
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import uuid
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func
from PIL import Image
import io
from flask_wtf.csrf import generate_csrf
from translations import translations
import jdatetime
from utils.zarinpal import create_payment_request, verify_payment

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///supermarket.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_ADDRESSES'] = 10
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
app.config['SESSION_TYPE'] = 'filesystem'

# Language configuration - Farsi only
# app.config['LANGUAGES'] = ['en', 'fa']  # English language removed
app.config['LANGUAGES'] = ['fa']  # Only Farsi language
app.config['DEFAULT_LANGUAGE'] = 'fa'

# Ensure upload directory exists
os.makedirs(os.path.join(app.root_path, app.config['UPLOAD_FOLDER']), exist_ok=True)

DEFAULT_IMAGE_URL = '/static/images/logo.jpeg'

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
migrate.init_app(app, db)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

def get_language():
    # Force Farsi language only
    return 'fa'  # Always return Farsi, no language switching

def get_translation(key):
    """Get translation for the current language - Farsi only"""
    # Always use Farsi translations
    return translations['fa'].get(key, key)

def flash_translated(message_key, category='message', **kwargs):
    """Flash a translated message with optional parameter substitution"""
    message = get_translation(message_key)
    if kwargs:
        # Support parameter substitution using .format()
        try:
            message = message.format(**kwargs)
        except (KeyError, ValueError):
            # If formatting fails, use the message as-is
            pass
    flash(message, category)

login_manager.login_message = 'login_required_message'

def localize_login_message(message):
    if message == 'login_required_message':
        return get_translation('login_required_message')
    return message

login_manager.localize_callback = localize_login_message

def get_image_or_default(image_path):
    """Return the provided image path or the default logo."""
    if image_path and isinstance(image_path, str) and image_path.strip():
        return image_path
    return DEFAULT_IMAGE_URL

# Language switching removed - Farsi only
# @app.route('/set_language/<language>')
# def set_language(language):
#     if language in app.config['LANGUAGES']:
#         session['language'] = language
#     return redirect(request.referrer or url_for('index'))

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
def inject_timestamp():
    """Inject timestamp for cache busting"""
    import time
    import os
    # Use file modification time for logo to ensure it refreshes when logo is updated
    logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.jpeg')
    if os.path.exists(logo_path):
        logo_mtime = int(os.path.getmtime(logo_path))
    else:
        logo_mtime = int(time.time())
    return dict(timestamp=logo_mtime)

def cleanup_old_cart_items():
    """Remove cart items older than 1 hour for all users"""
    try:
        # Get current time in UTC (timezone-aware)
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(hours=1)
        
        # Filter out NULL values and items older than 1 hour
        # Handle both timezone-aware and timezone-naive datetimes
        old_items = CartItem.query.filter(
            CartItem.created_at.isnot(None)
        ).all()
        
        # Filter items that are older than 1 hour
        expired_items = []
        for item in old_items:
            if item.created_at:
                # Convert timezone-naive to timezone-aware if needed
                item_time = item.created_at
                if item_time.tzinfo is None:
                    # Assume UTC if timezone-naive
                    from datetime import timezone as tz
                    item_time = item_time.replace(tzinfo=tz.utc)
                
                # Compare with cutoff date
                if item_time < cutoff_date:
                    expired_items.append(item)
        
        count = len(expired_items)
        if expired_items:
            for item in expired_items:
                db.session.delete(item)
            db.session.commit()
        return count
    except Exception as e:
        # If column doesn't exist or other error, just return 0
        # The database will need to be migrated or recreated
        print(f"Warning: Could not cleanup old cart items: {e}")
        return 0

@app.context_processor
def inject_cart_count():
    if current_user.is_authenticated:
        # Clean up old cart items periodically (only once per request to avoid overhead)
        if not hasattr(current_app, '_cart_cleanup_done'):
            cleanup_old_cart_items()
            current_app._cart_cleanup_done = True
        cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
    else:
        cart_count = 0
    return dict(cart_count=cart_count)

@app.context_processor
def inject_image_defaults():
    return dict(
        default_image_url=DEFAULT_IMAGE_URL,
        get_image_or_default=get_image_or_default
    )

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
    # Get categories from Category model, fallback to product categories
    category_objects = Category.query.all()
    product_categories = list(set([p.category for p in Product.query.all() if p.category]))
    # Merge both sources
    all_category_names = set([cat.name for cat in category_objects] + product_categories)
    categories = sorted(list(all_category_names))
    
    # Create a dict to map category names to category objects
    category_dict = {cat.name: cat for cat in category_objects}
    
    # Get all brands with products
    brands = Brand.query.all()
    
    # Get products by brand
    products_by_brand = {}
    for brand in brands:
        products = Product.query.options(joinedload(Product.brand)).filter_by(brand_id=brand.id).all()
        if products:  # Only include brands that have products
            products_by_brand[brand] = products
    
    # Convert to list for template (limit to first 3 brands)
    brands_with_products = list(products_by_brand.items())[:3]
    
    # Get featured products with brand
    featured_products = Product.query.options(joinedload(Product.brand)).filter_by(is_featured=True).all()
    
    # Get products by category with brand
    products_by_category = {}
    for category in categories:
        products = Product.query.options(joinedload(Product.brand)).filter_by(category=category).all()
        products_by_category[category] = products
    
    return render_template('index.html', 
                         categories=categories,
                         category_dict=category_dict,
                         brands=brands,
                         products_by_brand=products_by_brand,
                         brands_with_products=brands_with_products,
                         featured_products=featured_products,
                         products_by_category=products_by_category)

@app.route('/category/<category>')
def category(category):
    products = Product.query.options(joinedload(Product.brand)).filter_by(category=category).all()
    return render_template('category.html', products=products, category=category)

@app.route('/support')
def support():
    """Support page with contact information"""
    return render_template('support.html')

@app.route('/brand/<int:brand_id>')
def brand(brand_id):
    brand = Brand.query.get_or_404(brand_id)
    products = Product.query.options(joinedload(Product.brand)).filter_by(brand_id=brand_id).all()
    return render_template('brand.html', products=products, brand=brand)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get statistics
    total_products = Product.query.count()
    total_users = User.query.count()
    total_orders = Order.query.count()
    # Get categories from Category model, fallback to product categories for backward compatibility
    category_objects = Category.query.all()
    product_categories = list(set([p.category for p in Product.query.all() if p.category]))
    # Merge both sources
    all_category_names = set([cat.name for cat in category_objects] + product_categories)
    categories = sorted(list(all_category_names))
    locations = StoreLocation.query.all()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    products = Product.query.all()
    brands = Brand.query.all()
    
    search_query = request.args.get('search', '').strip()
    search_scope = request.args.get('scope', 'all')
    allowed_scopes = {'all', 'products', 'brands', 'categories'}
    if search_scope not in allowed_scopes:
        search_scope = 'all'
    
    filtered_products = products
    filtered_brands = brands
    filtered_categories = categories
    search_summary = []
    
    if search_query:
        term = search_query.lower()
        
        if search_scope in ('all', 'products'):
            filtered_products = [
                product for product in products
                if term in (product.name or '').lower()
                or term in (product.category or '').lower()
                or (product.brand and term in (product.brand.name or '').lower())
            ]
            search_summary.append({'key': 'products', 'count': len(filtered_products)})
        
        if search_scope in ('all', 'brands'):
            filtered_brands = [
                brand for brand in brands
                if term in (brand.name or '').lower()
            ]
            search_summary.append({'key': 'brands', 'count': len(filtered_brands)})
        
        if search_scope in ('all', 'categories'):
            filtered_categories = [
                category for category in categories
                if category and term in category.lower()
            ]
            search_summary.append({'key': 'categories', 'count': len(filtered_categories)})
        else:
            # Ensure categories remain unchanged if not part of the search scope
            filtered_categories = categories
    else:
        filtered_products = products
        filtered_brands = brands
        filtered_categories = categories
    
    # Get delivery fee from session or use default
    delivery_fee = session.get('delivery_fee', 20000)
    
    return render_template('admin/dashboard.html',
                         total_products=total_products,
                         total_users=total_users,
                         total_orders=total_orders,
                         categories=categories,
                         category_objects=category_objects,
                         locations=locations,
                         recent_orders=recent_orders,
                         products=products,
                         brands=brands,
                         delivery_fee=delivery_fee,
                         filtered_products=filtered_products,
                         filtered_brands=filtered_brands,
                         filtered_categories=filtered_categories,
                         search_query=search_query,
                         search_scope=search_scope,
                         search_summary=search_summary)

@app.route('/admin/update_delivery_settings', methods=['POST'])
@admin_required
def admin_update_delivery_settings():
    try:
        delivery_fee = float(request.form.get('delivery_fee', 20000))
        
        if delivery_fee < 0:
            flash_translated('invalid_delivery_fee', 'error')
            return redirect(url_for('admin_dashboard'))
        
        session['delivery_fee'] = delivery_fee
        
        flash_translated('delivery_settings_updated', 'success')
    except ValueError:
        flash_translated('invalid_delivery_fee', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash_translated('access_denied', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            price = float(request.form.get('price'))
            stock = int(request.form.get('stock'))
            category = request.form.get('category')
            brand_id = request.form.get('brand_id')
            brand_id = int(brand_id) if brand_id and brand_id != '' else None
            discount = float(request.form.get('discount', 0))
            is_featured = 'is_featured' in request.form
            
            # Handle image - either file upload or URL
            image_url = handle_image_input(
                image_file=request.files.get('image') if 'image' in request.files else None,
                image_url=request.form.get('image_url'),
                folder='products'
            )
            
            product = Product(
                name=name,
                description=description,
                price=price,
                stock=stock,
                category=category,
                brand_id=brand_id,
                image_url=get_image_or_default(image_url),
                discount=discount,
                is_featured=is_featured
            )
            
            db.session.add(product)
            db.session.commit()
            
            flash_translated('item_added', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding product: {str(e)}")
            flash_translated('error_adding_product', 'error')
            return redirect(url_for('admin_add_product'))
    
    # Get all categories for the form
    # Get categories from Category model, fallback to product categories for backward compatibility
    category_objects = Category.query.all()
    product_categories = list(set([p.category for p in Product.query.all() if p.category]))
    # Merge both sources
    all_category_names = set([cat.name for cat in category_objects] + product_categories)
    categories = sorted(list(all_category_names))
    
    # Get all brands for the form
    brands = Brand.query.all()
    
    return render_template('admin/add_product.html', categories=categories, brands=brands)

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if not current_user.is_admin:
        flash_translated('access_denied', 'danger')
        return redirect(url_for('index'))
    
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        try:
            product.name = request.form.get('name')
            product.description = request.form.get('description')
            product.price = float(request.form.get('price'))
            product.stock = int(request.form.get('stock'))
            product.category = request.form.get('category')
            brand_id = request.form.get('brand_id')
            product.brand_id = int(brand_id) if brand_id and brand_id != '' else None
            product.discount = float(request.form.get('discount', 0))
            product.is_featured = 'is_featured' in request.form
            
            # Handle image - either file upload or URL
            new_image_url = handle_image_input(
                image_file=request.files.get('image') if 'image' in request.files else None,
                image_url=request.form.get('image_url'),
                folder='products'
            )
            
            if new_image_url:
                # Delete old image if it exists and is a local file
                if product.image_url and product.image_url.startswith('/static/uploads/'):
                    old_image_path = os.path.join(app.root_path, product.image_url.lstrip('/'))
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except:
                            pass  # Ignore errors deleting old file
                product.image_url = new_image_url
            
            product.image_url = get_image_or_default(product.image_url)

            db.session.commit()
            flash_translated('item_updated', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            print(f"Error updating product: {str(e)}")
            flash_translated('error_updating_product', 'error')
            return redirect(url_for('admin_edit_product', product_id=product_id))
    
    # Get all categories for the form
    # Get categories from Category model, fallback to product categories for backward compatibility
    category_objects = Category.query.all()
    product_categories = list(set([p.category for p in Product.query.all() if p.category]))
    # Merge both sources
    all_category_names = set([cat.name for cat in category_objects] + product_categories)
    categories = sorted(list(all_category_names))
    
    # Get all brands for the form
    brands = Brand.query.all()
    
    return render_template('admin/edit_product.html', product=product, categories=categories, brands=brands)

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

@app.route('/admin/category/add', methods=['GET', 'POST'])
@admin_required
def admin_add_category():
    if request.method == 'POST':
        category_name = request.form.get('category_name')
        if category_name:
            # Check if category already exists
            existing_category = Category.query.filter_by(name=category_name).first()
            if not existing_category:
                # Handle image - either file upload or URL
                image_url = handle_image_input(
                    image_file=request.files.get('image') if 'image' in request.files else None,
                    image_url=request.form.get('image_url'),
                    folder='categories'
                )
                
                # Create category
                category = Category(name=category_name, image_url=get_image_or_default(image_url))
                db.session.add(category)
                db.session.commit()
                flash_translated('category_added', 'success')
            else:
                flash_translated('category_exists', 'error')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/add_category.html')

@app.route('/admin/category/edit/<category>', methods=['GET', 'POST'])
@admin_required
def admin_edit_category(category):
    # Try to find category by name (for backward compatibility) or by ID
    category_obj = Category.query.filter_by(name=category).first()
    if not category_obj:
        # If category doesn't exist in Category model, create it
        category_obj = Category(name=category, image_url=DEFAULT_IMAGE_URL)
        db.session.add(category_obj)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            new_name = request.form.get('category_name')
            if new_name and new_name != category_obj.name:
                # Check if new name already exists
                existing = Category.query.filter_by(name=new_name).first()
                if existing and existing.id != category_obj.id:
                    flash_translated('category_exists', 'error')
                    return redirect(url_for('admin_edit_category', category=category))
                
                # Update category name
                old_name = category_obj.name
                category_obj.name = new_name
                
                # Update all products in this category (for backward compatibility)
                Product.query.filter_by(category=old_name).update({'category': new_name})
            
            # Handle image - either file upload or URL
            new_image_url = handle_image_input(
                image_file=request.files.get('image') if 'image' in request.files else None,
                image_url=request.form.get('image_url'),
                folder='categories'
            )
            
            if new_image_url:
                # Delete old image if it exists and is a local file
                if category_obj.image_url and category_obj.image_url.startswith('/static/uploads/'):
                    old_image_path = os.path.join(app.root_path, category_obj.image_url.lstrip('/'))
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except:
                            pass  # Ignore errors deleting old file
                category_obj.image_url = new_image_url
            
            category_obj.image_url = get_image_or_default(category_obj.image_url)

            db.session.commit()
            flash_translated('category_updated', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            print(f"Error updating category: {str(e)}")
            flash_translated('error_updating_category', 'error')
            return redirect(url_for('admin_edit_category', category=category))
    
    return render_template('admin/edit_category.html', category=category_obj)

@app.route('/admin/category/delete/<category>')
@admin_required
def admin_delete_category(category):
    try:
        # Find category object
        category_obj = Category.query.filter_by(name=category).first()
        
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
        
        # Delete category image if it exists and is a local file
        if category_obj:
            if category_obj.image_url and category_obj.image_url.startswith('/static/uploads/'):
                old_image_path = os.path.join(app.root_path, category_obj.image_url.lstrip('/'))
                if os.path.exists(old_image_path):
                    try:
                        os.remove(old_image_path)
                    except:
                        pass
            # Delete category object
            db.session.delete(category_obj)
        
        db.session.commit()
        flash_translated('category_and_products_deleted', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting category: {str(e)}")
        flash_translated('error_deleting_category', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/brand/add', methods=['GET', 'POST'])
@admin_required
def admin_add_brand():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            if not name:
                flash_translated('brand_name_required', 'error')
                return redirect(url_for('admin_add_brand'))
            
            # Check if brand already exists
            existing_brand = Brand.query.filter_by(name=name).first()
            if existing_brand:
                flash_translated('brand_exists', 'error')
                return redirect(url_for('admin_add_brand'))
            
            # Handle image - either file upload or URL
            image_url = handle_image_input(
                image_file=request.files.get('image') if 'image' in request.files else None,
                image_url=request.form.get('image_url'),
                folder='brands'
            )
            
            brand = Brand(name=name, image_url=get_image_or_default(image_url))
            db.session.add(brand)
            db.session.commit()
            
            flash_translated('brand_added', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding brand: {str(e)}")
            flash_translated('error_adding_brand', 'error')
            return redirect(url_for('admin_add_brand'))
    
    return render_template('admin/add_brand.html')

@app.route('/admin/brand/edit/<int:brand_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_brand(brand_id):
    brand = Brand.query.get_or_404(brand_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            if not name:
                flash_translated('brand_name_required', 'error')
                return redirect(url_for('admin_edit_brand', brand_id=brand_id))
            
            # Check if another brand with the same name exists
            existing_brand = Brand.query.filter(Brand.name == name, Brand.id != brand_id).first()
            if existing_brand:
                flash_translated('brand_exists', 'error')
                return redirect(url_for('admin_edit_brand', brand_id=brand_id))
            
            brand.name = name
            
            # Handle image - either file upload or URL
            new_image_url = handle_image_input(
                image_file=request.files.get('image') if 'image' in request.files else None,
                image_url=request.form.get('image_url'),
                folder='brands'
            )
            
            if new_image_url:
                # Delete old image if it exists and is a local file
                if brand.image_url and brand.image_url.startswith('/static/uploads/'):
                    old_image_path = os.path.join(app.root_path, brand.image_url.lstrip('/'))
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except:
                            pass  # Ignore errors deleting old file
                brand.image_url = new_image_url
            
            brand.image_url = get_image_or_default(brand.image_url)

            db.session.commit()
            flash_translated('brand_updated', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            print(f"Error updating brand: {str(e)}")
            flash_translated('error_updating_brand', 'error')
            return redirect(url_for('admin_edit_brand', brand_id=brand_id))
    
    return render_template('admin/edit_brand.html', brand=brand)

@app.route('/admin/brand/delete/<int:brand_id>', methods=['POST'])
@admin_required
def admin_delete_brand(brand_id):
    try:
        brand = Brand.query.get_or_404(brand_id)
        
        # Check if brand has any products
        products_with_brand = Product.query.filter_by(brand_id=brand_id).all()
        if products_with_brand:
            # Remove brand from products (set brand_id to None)
            for product in products_with_brand:
                product.brand_id = None
            db.session.commit()
        
        # Delete brand image if it exists
        if brand.image_url and brand.image_url.startswith('/static/uploads/'):
            old_image_path = os.path.join(app.root_path, brand.image_url.lstrip('/'))
            if os.path.exists(old_image_path):
                os.remove(old_image_path)
        
        # Delete the brand
        db.session.delete(brand)
        db.session.commit()
        
        flash_translated('brand_deleted', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting brand: {str(e)}")
        flash_translated('error_deleting_brand', 'error')
    
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
            
            # Special case for admin phone number - bypass verification
            if formatted_phone == '+989131111111':
                if user is None:
                    # Create new admin user
                    user = User(
                        username='Admin',
                        phone_number=formatted_phone,
                        is_admin=True  # Set as admin
                    )
                    db.session.add(user)
                    db.session.flush()
                    
                    # Wallet feature removed
                else:
                    # Ensure existing user is admin
                    if not user.is_admin:
                        user.is_admin = True
                        db.session.commit()
                
                # Log in the admin user directly
                login_user(user)
                session.pop('login_step', None)
                session.pop('login_phone', None)
                
                # If this is a new admin user, redirect to profile setup
                if not user.username or user.username.startswith('Admin_'):
                    return redirect(url_for('profile'))
                
                next_page = request.args.get('next')
                if not next_page or not next_page.startswith('/'):
                    next_page = url_for('admin_dashboard')  # Redirect to admin dashboard by default
                return redirect(next_page)
            
            # Normal flow for other phone numbers
            if user is None:
                try:
                    # Create new user
                    user = User(
                        username=f"User_{formatted_phone[-4:]}",
                        phone_number=formatted_phone,
                        is_admin=False
                    )
                    db.session.add(user)
                    db.session.flush()
                    
                    # Wallet feature removed
                    
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
            phone_number=form.phone_number.data
        )
        db.session.add(user)
        db.session.commit()
        # Wallet feature removed
        
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
    # Clean up old cart items (older than 1 hour) for all users
    cleanup_old_cart_items()
    
    # Get cart items after cleanup (only non-expired items)
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    
    # Filter out any items that might have expired (safety check)
    valid_cart_items = []
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(hours=1)
    
    for item in cart_items:
        if item.created_at:
            # Ensure timezone-aware datetime
            item_time = item.created_at
            if item_time.tzinfo is None:
                item_time = item_time.replace(tzinfo=timezone.utc)
            
            # Only include items that haven't expired
            if item_time >= cutoff_date:
                valid_cart_items.append(item)
            else:
                # Item expired, delete it
                db.session.delete(item)
    
    # Commit any deletions
    if len(valid_cart_items) < len(cart_items):
        db.session.commit()
        cart_items = valid_cart_items
    
    # Calculate cart expiration time (1 hour from oldest item)
    cart_expires_at = None
    if cart_items:
        # Find the oldest cart item
        oldest_item = min(cart_items, key=lambda x: x.created_at if x.created_at else datetime.now(timezone.utc))
        if oldest_item.created_at:
            # Ensure timezone-aware datetime
            oldest_time = oldest_item.created_at
            if oldest_time.tzinfo is None:
                # Convert timezone-naive to timezone-aware (assume UTC)
                oldest_time = oldest_time.replace(tzinfo=timezone.utc)
            
            # Calculate expiration: 1 hour from when the oldest item was created
            expiration_time = oldest_time + timedelta(hours=1)
            # Convert to UTC timestamp for JavaScript (milliseconds)
            cart_expires_at = int(expiration_time.timestamp() * 1000)
    
    # Calculate subtotal without discounts
    subtotal = sum(
        item.product.price * item.quantity 
        for item in cart_items
    )
    
    # Get delivery fee from session or use default
    delivery_fee = session.get('delivery_fee', 20000)
    
    # Calculate total
    total = subtotal + delivery_fee
    
    # Get user's addresses and store locations
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    locations = StoreLocation.query.filter_by(is_active=True).order_by(StoreLocation.id).all()
    
    # Get first active location as default
    default_location = locations[0] if locations else None
    
    # Wallet feature removed
    
    return render_template('cart.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         delivery_fee=delivery_fee,
                         total=total,
                         addresses=addresses,
                         locations=locations,
                         default_location=default_location,
                         cart_expires_at=cart_expires_at)

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
        flash_translated('only_x_items_available_in_stock', 'danger', x=cart_item.product.stock)
        return redirect(url_for('cart'))
    
    cart_item.quantity = quantity
    # Update the updated_at timestamp (but keep created_at unchanged)
    cart_item.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    
    flash_translated('cart_updated')
    return redirect(url_for('cart'))

@app.route('/add_to_cart/<int:product_id>', methods=['GET', 'POST'])
@login_required
def add_to_cart(product_id):
    # Clean up old cart items before adding new ones
    cleanup_old_cart_items()
    
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    
    # Validate quantity
    if quantity < 1:
        flash_translated('quantity_must_be_at_least_1', 'danger')
        return redirect(request.referrer or url_for('index'))
    
    # Get existing cart item if any
    cart_item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()
    
    # Calculate available stock (total stock minus what's already in cart)
    current_cart_quantity = cart_item.quantity if cart_item else 0
    available_stock = product.stock - current_cart_quantity
    
    # Check if user has already ordered all available stock
    if current_cart_quantity >= product.stock:
        flash_translated('all_stock_ordered', 'danger')
        return redirect(request.referrer or url_for('index'))
    
    # Check if requested quantity exceeds available stock
    if quantity > available_stock:
        flash_translated('only_x_items_available_in_stock', 'danger', x=available_stock)
        return redirect(request.referrer or url_for('index'))
    
    # Add or update cart item
    if cart_item:
        # Update existing item - keep original created_at timestamp
        cart_item.quantity += quantity
        # Update the updated_at timestamp
        cart_item.updated_at = datetime.now(timezone.utc)
    else:
        # Create new item with explicit timestamp
        cart_item = CartItem(
            user_id=current_user.id, 
            product_id=product_id, 
            quantity=quantity,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
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
        current_user.username = form.username.data
        current_user.phone_number = form.phone_number.data
        
        db.session.commit()
        flash_translated('profile_updated')
        return redirect(url_for('profile'))

    # Pre-fill form with current user data
    if request.method == 'GET':
        form.username.data = current_user.username
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

# Verification feature removed

@app.route('/admin/users')
@admin_required
def admin_users():
    # Get search query and page number
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Base query with orders loaded
    query = User.query.options(joinedload(User.orders))
    
    # Apply search filter
    if search_query:
        search_term = f'%{search_query}%'
        query = query.filter(
            or_(
                User.username.ilike(search_term),
                User.phone_number.ilike(search_term)
            )
        )
    
    # Order by creation date (newest first) and paginate
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    users = pagination.items
    
    # Get order counts for each user
    for user in users:
        user.order_count = len(user.orders)
        user.total_spent = sum(order.total_amount for order in user.orders)
    
    return render_template('admin/users.html', 
                         users=users, 
                         search_query=search_query,
                         pagination=pagination)

@app.route('/api/search/autocomplete')
def search_autocomplete():
    """API endpoint for search autocomplete suggestions"""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    
    # Search products
    products = Product.query.options(joinedload(Product.brand)).filter(
        or_(
            Product.name.ilike(f'%{query}%'),
            Product.description.ilike(f'%{query}%'),
            Product.category.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    suggestions = []
    for product in products:
        suggestions.append({
            'id': product.id,
            'name': product.name,
            'category': product.category,
            'brand': product.brand.name if product.brand else None,
            'image': product.image_url,
            'type': 'product'
        })
    
    # Search categories
    categories = Category.query.filter(Category.name.ilike(f'%{query}%')).limit(5).all()
    for category in categories:
        suggestions.append({
            'id': category.id,
            'name': category.name,
            'type': 'category'
        })
    
    # Search brands
    brands = Brand.query.filter(Brand.name.ilike(f'%{query}%')).limit(5).all()
    for brand in brands:
        suggestions.append({
            'id': brand.id,
            'name': brand.name,
            'image': brand.image_url,
            'type': 'brand'
        })
    
    return jsonify(suggestions)

@app.route('/api/admin/search/autocomplete')
@admin_required
def admin_search_autocomplete():
    """API endpoint for admin dashboard search autocomplete"""
    query = request.args.get('q', '').strip()
    scope = request.args.get('scope', 'all')
    
    if not query or len(query) < 2:
        return jsonify([])
    
    suggestions = []
    term = query.lower()
    
    if scope in ('all', 'products'):
        products = Product.query.options(joinedload(Product.brand)).filter(
            or_(
                Product.name.ilike(f'%{query}%'),
                Product.category.ilike(f'%{query}%')
            )
        ).limit(10).all()
        for product in products:
            suggestions.append({
                'id': product.id,
                'name': product.name,
                'category': product.category,
                'brand': product.brand.name if product.brand else None,
                'type': 'product'
            })
    
    if scope in ('all', 'brands'):
        brands = Brand.query.filter(Brand.name.ilike(f'%{query}%')).limit(5).all()
        for brand in brands:
            suggestions.append({
                'id': brand.id,
                'name': brand.name,
                'type': 'brand'
            })
    
    if scope in ('all', 'categories'):
        categories = Category.query.filter(Category.name.ilike(f'%{query}%')).limit(5).all()
        for category in categories:
            suggestions.append({
                'id': category.id,
                'name': category.name,
                'type': 'category'
            })
    
    return jsonify(suggestions)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    
    # Filter parameters
    sort_by = request.args.get('sort', 'relevance')  # relevance, price_low, price_high, newest, oldest, most_ordered
    brand_filter = request.args.get('brand', '')
    category_filter = request.args.get('category', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    featured_only = request.args.get('featured', '') == 'on'
    discounted_only = request.args.get('discounted', '') == 'on'
    
    # Base query
    if query:
        products_query = Product.query.options(joinedload(Product.brand)).filter(
            or_(
                Product.name.ilike(f'%{query}%'),
                Product.description.ilike(f'%{query}%'),
                Product.category.ilike(f'%{query}%')
            )
        )
    else:
        products_query = Product.query.options(joinedload(Product.brand))
    
    # Apply filters
    if brand_filter:
        try:
            products_query = products_query.filter(Product.brand_id == int(brand_filter))
        except (ValueError, TypeError):
            pass
    
    if category_filter:
        products_query = products_query.filter(Product.category == category_filter)
    
    if featured_only:
        products_query = products_query.filter(Product.is_featured == True)
    
    if discounted_only:
        products_query = products_query.filter(Product.discount > 0)
    
    if min_price:
        try:
            min_val = float(min_price)
            products_query = products_query.filter(Product.price >= min_val)
        except ValueError:
            pass
    
    if max_price:
        try:
            max_val = float(max_price)
            products_query = products_query.filter(Product.price <= max_val)
        except ValueError:
            pass
    
    # Apply sorting
    if sort_by == 'price_low':
        products_query = products_query.order_by(Product.price.asc())
    elif sort_by == 'price_high':
        products_query = products_query.order_by(Product.price.desc())
    elif sort_by == 'newest':
        products_query = products_query.order_by(Product.created_at.desc())
    elif sort_by == 'oldest':
        products_query = products_query.order_by(Product.created_at.asc())
    elif sort_by == 'most_ordered':
        # Order by order count (calculated dynamically)
        products_query = products_query.outerjoin(OrderItem).group_by(Product.id).order_by(func.coalesce(func.sum(OrderItem.quantity), 0).desc())
    else:  # relevance (default)
        if not query:
            products_query = products_query.order_by(Product.created_at.desc())
    
    products = products_query.all()
    
    # Get available brands and categories for filters
    all_brands = Brand.query.all()
    all_categories = list(set([p.category for p in Product.query.all() if p.category]))
    
    return render_template('search_results.html', 
                         products=products, 
                         query=query,
                         sort_by=sort_by,
                         brand_filter=brand_filter,
                         category_filter=category_filter,
                         min_price=min_price,
                         max_price=max_price,
                         featured_only=featured_only,
                         discounted_only=discounted_only,
                         all_brands=all_brands,
                         all_categories=all_categories)

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    
    if not cart_items:
        flash_translated('cart_empty', 'error')
        return redirect(url_for('cart'))
    
    # Calculate subtotal without discounts
    subtotal = sum(
        item.product.price * item.quantity 
        for item in cart_items
    )
    
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
            # Get delivery fee from session or use default
            delivery_fee = session.get('delivery_fee', 20000)
        
        # Calculate total with delivery fee
        total = subtotal + delivery_fee
        
        # Payment method is always online
        payment_method = 'online'
        
        # Check if user has special phone number to skip payment
        special_phone = '+989131111111'
        skip_payment = current_user.phone_number == special_phone
        
        if skip_payment:
            # Skip payment and create order directly
            try:
                # Create order directly
                order = Order(
                    user_id=current_user.id,
                    total_amount=total,
                    delivery_fee=delivery_fee,
                    status='pending_approval',
                    payment_method='online',
                    delivery_type=delivery_type,
                    store_location_id=store_location_id if delivery_type == 'pickup' else None,
                    address_id=address_id if delivery_type == 'delivery' else None,
                    description=request.form.get('order_description', '').strip()
                )
                db.session.add(order)
                db.session.flush()  # Get order ID
                
                # Get cart items
                cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
                
                if not cart_items:
                    db.session.rollback()
                    flash_translated('cart_empty', 'error')
                    return redirect(url_for('cart'))
                
                # Add order items from cart
                for item in cart_items:
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=item.product_id,
                        quantity=item.quantity,
                        price=item.product.price
                    )
                    db.session.add(order_item)
                    
                    # Update product stock
                    item.product.stock -= item.quantity
                
                # Commit order and order items
                db.session.commit()
                
                # Clear cart after successful commit
                for item in cart_items:
                    db.session.delete(item)
                db.session.commit()
                
                flash_translated('order_placed_successfully', 'success')
                return redirect(url_for('order_status', order_id=order.id))
                
            except Exception as e:
                db.session.rollback()
                print(f"Error creating order: {str(e)}")
                flash_translated('error_creating_order', 'error')
                return redirect(url_for('cart'))
        
        if payment_method == 'online':
            # Store order details in session for payment success
            session['order_total'] = total
            session['payment_method'] = payment_method
            session['delivery_type'] = delivery_type
            session['store_location_id'] = store_location_id if delivery_type == 'pickup' else None
            session['address_id'] = address_id if delivery_type == 'delivery' else None
            session['order_description'] = request.form.get('order_description', '').strip()

            # Create ZarinPal payment request
            description = f"Order payment for {current_user.username}"
            callback_url = url_for('zarinpal_verify', _external=True)
            
            # Convert total to integer (ZarinPal expects amount in Tomans)
            amount_in_tomans = int(total)
            
            status, authority = create_payment_request(
                amount=amount_in_tomans,
                description=description,
            email=None,
                callback_url=callback_url
            )
            
            if status == 100 and authority:
                # Store authority and amount in session for verification
                session['zarinpal_authority'] = authority
                session['zarinpal_amount'] = amount_in_tomans
                return redirect(f'https://www.zarinpal.com/pg/StartPay/{authority}')
            else:
                flash_translated('payment_gateway_error', 'error')
                return redirect(url_for('cart'))
    
    # For GET request, calculate delivery fee for display
    delivery_fee = session.get('delivery_fee', 20000)  # Get delivery fee from session or use default
    total = subtotal + delivery_fee
    
    # Get user's addresses and store locations
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    locations = StoreLocation.query.filter_by(is_active=True).order_by(StoreLocation.id).all()
    
    # Get first active location as default
    default_location = locations[0] if locations else None
    
    return render_template('cart.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         delivery_fee=delivery_fee,
                         total=total,
                         addresses=addresses,
                         locations=locations,
                         default_location=default_location)

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
        is_active = 'is_active' in request.form
        
        location = StoreLocation(
            name=name,
            address=address,
            description=None,
            latitude=None,
            longitude=None,
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
    # Get order comment if it exists
    order_comment = OrderComment.query.filter_by(order_id=order_id).first()
    return render_template('admin/order_details.html', order=order, order_comment=order_comment)

@app.cli.command("create-admin")
def create_admin():
    """Create the admin user if it doesn't exist"""
    admin = User.query.filter_by(phone_number='+989137597568').first()
    if not admin:
        admin = User(
            username='Admin',
            phone_number='+989137597568',
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")
    else:
        print("Admin user already exists!")

@app.cli.command("create-store")
def create_store():
    """Create a default store location"""
    try:
        # Check if store already exists
        existing_store = StoreLocation.query.filter_by(name='فروشگاه اصلی').first()
        if existing_store:
            print("Store already exists!")
            return

        # Create new store
        store = StoreLocation(
            name='فروشگاه اصلی',
            address='تهران، خیابان ولیعصر، پلاک 123',
            description='فروشگاه اصلی در مرکز شهر',
            latitude=35.6892,  # Tehran coordinates
            longitude=51.3890,
            is_active=True
        )
        
        db.session.add(store)
        db.session.commit()
        print("Store created successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating store: {str(e)}")

# Add this to the init_db function
def init_db():
    """Initialize the database"""
    with app.app_context():
        db.create_all()
        # Clean up old cart items on startup (only if column exists)
        # If the column doesn't exist yet, it will be created by db.create_all()
        # and cleanup will work on next startup
        try:
            cleanup_old_cart_items()
        except Exception:
            # Column might not exist yet, that's okay - it will be created
            pass
        # Create admin user
        admin = User.query.filter_by(phone_number='+989137597568').first()
        if not admin:
            admin = User(
                username='Admin',
                phone_number='+989137597568',
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")
        
        # Create default store
        store = StoreLocation.query.filter_by(name='فروشگاه اصلی').first()
        if not store:
            store = StoreLocation(
                name='فروشگاه اصلی',
                address='تهران، خیابان ولیعصر، پلاک 123',
                description='فروشگاه اصلی در مرکز شهر',
                latitude=35.6892,  # Tehran coordinates
                longitude=51.3890,
                is_active=True
            )
            db.session.add(store)
            db.session.commit()
            print("Default store created successfully!")

# Wallet feature removed

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
    
    # Wallet feature removed (no wallet refunds)
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
    
    # Wallet feature removed (no wallet refunds)
    db.session.commit()
    flash(get_translation('order_cancelled'), 'success')
    return redirect(url_for('admin_order_details', order_id=order_id))

@app.route('/product/<int:product_id>')
def product_details(product_id):
    product = Product.query.options(joinedload(Product.brand)).get_or_404(product_id)
    
    return render_template('product_details.html', product=product)

def optimize_image(image, max_size_kb=100, max_dimension=2000):
    """
    Optimize image to PNG or JPG format with maximum file size
    Returns optimized image bytes and format
    """
    try:
        # Read image data
        image_data = image.read()
        image.seek(0)  # Reset for potential fallback
        
        # Open image
        img = Image.open(io.BytesIO(image_data))
        
        # Convert RGBA to RGB if necessary (for JPG compatibility)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if too large
        width, height = img.size
        if width > max_dimension or height > max_dimension:
            ratio = min(max_dimension / width, max_dimension / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Try to compress to target size
        max_bytes = max_size_kb * 1024
        output_format = 'JPEG'  # Default to JPEG for better compression
        quality = 85
        output = None
        
        # Try different quality levels to get under max_size_kb
        for attempt in range(10):
            output = io.BytesIO()
            img.save(output, format=output_format, quality=quality, optimize=True)
            size = output.tell()
            
            if size <= max_bytes:
                break
            
            # Reduce quality
            quality -= 10
            if quality < 20:
                # If still too large, try resizing more
                width, height = img.size
                img = img.resize((int(width * 0.9), int(height * 0.9)), Image.Resampling.LANCZOS)
                quality = 85
        
        # If still too large, resize more aggressively
        while output and output.tell() > max_bytes and (img.size[0] > 100 or img.size[1] > 100):
            width, height = img.size
            img = img.resize((int(width * 0.8), int(height * 0.8)), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            img.save(output, format=output_format, quality=50, optimize=True)
        
        if output:
            output.seek(0)
            return output, output_format.lower()
        else:
            return None, None
    except Exception as e:
        print(f"Error optimizing image: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None

def handle_image_input(image_file=None, image_url=None, folder='products'):
    """
    Handle image input - either from file upload or URL
    Returns the image URL (either uploaded optimized file path or provided URL)
    """
    # Priority: file upload > URL
    if image_file and image_file.filename:
        # Handle file upload
        return save_file(image_file, folder)
    elif image_url and image_url.strip():
        # Handle URL - validate it's a proper URL
        url = image_url.strip()
        if url.startswith('http://') or url.startswith('https://'):
            return url
        elif url.startswith('/'):
            # Relative URL
            return url
        else:
            # Invalid URL format
            return None
    return None

def save_file(file, folder):
    """Save an uploaded file securely with image optimization"""
    if file and file.filename:
        try:
            # Check if it's an image file
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            
            # Create unique filename with timestamp
            unique_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Create folder path
            folder_path = os.path.join(app.root_path, 'static', 'uploads', folder)
            # Ensure folder exists
            os.makedirs(folder_path, exist_ok=True)
            
            # If it's an image, optimize it
            if file_ext in allowed_extensions:
                # Reset file pointer
                file.seek(0)
                
                # Optimize image
                optimized_image, img_format = optimize_image(file, max_size_kb=100)
                
                if optimized_image:
                    # Use optimized format (jpg or png)
                    final_ext = 'jpg' if img_format == 'jpeg' else img_format
                    unique_filename = f"{timestamp}_{unique_id}.{final_ext}"
                    file_path = os.path.join(folder_path, unique_filename)
                    
                    # Save optimized image
                    with open(file_path, 'wb') as f:
                        f.write(optimized_image.read())
                    
                    # Return relative path for database
                    return f'/static/uploads/{folder}/{unique_filename}'
                else:
                    # Fallback to original save if optimization fails
                    filename = secure_filename(file.filename)
                    unique_filename = f"{timestamp}_{unique_id}_{filename}"
                    file_path = os.path.join(folder_path, unique_filename)
                    file.seek(0)
                    file.save(file_path)
                    return f'/static/uploads/{folder}/{unique_filename}'
            else:
                # For non-image files, save as-is
                filename = secure_filename(file.filename)
                unique_filename = f"{timestamp}_{unique_id}_{filename}"
                file_path = os.path.join(folder_path, unique_filename)
                file.save(file_path)
                return f'/static/uploads/{folder}/{unique_filename}'
                
        except Exception as e:
            print(f"Error saving file: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    return None


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
    # Get page numbers for both sections
    waiting_page = request.args.get('waiting_page', 1, type=int)
    completed_page = request.args.get('completed_page', 1, type=int)
    per_page = 10
    
    # Get all completed and rejected orders
    completed_orders_query = Order.query.filter(
        Order.status.in_(['completed', 'rejected'])
    ).order_by(Order.completed_at.desc())
    
    # Get all comments
    comments_query = OrderComment.query.join(Order).filter(
        Order.status.in_(['completed', 'rejected'])
    ).order_by(OrderComment.created_at.desc())
    
    # Get all comments to find which orders have comments
    all_comments = comments_query.all()
    commented_order_ids = {comment.order_id for comment in all_comments}
    
    # Get all completed orders
    all_completed_orders = completed_orders_query.all()
    
    # Separate waiting and completed entries
    waiting_entries_list = []
    completed_entries_list = []
    
    # Add actual comments
    for comment in all_comments:
        comment.is_waiting = False
        completed_entries_list.append(comment)
    
    # Add waiting entries for orders without comments (only completed orders, not rejected)
    for order in all_completed_orders:
        if order.id not in commented_order_ids and order.status == 'completed':
            # Use completed_at or created_at as fallback
            order_date = order.completed_at or order.created_at
            waiting_comment = type('WaitingComment', (), {
                'order': order,
                'created_at': order_date,
                'is_waiting': True,
                'food_quality': '-',
                'delivery_service': '-',
                'packaging': '-',
                'value_for_money': '-',
                'overall_experience': '-',
                'comment': None
            })
            waiting_entries_list.append(waiting_comment)
    
    # Sort both lists
    waiting_entries_list.sort(key=lambda x: x.created_at, reverse=True)
    completed_entries_list.sort(key=lambda x: x.created_at, reverse=True)
    
    # Paginate waiting entries
    waiting_total = len(waiting_entries_list)
    waiting_start = (waiting_page - 1) * per_page
    waiting_end = waiting_start + per_page
    waiting_entries = waiting_entries_list[waiting_start:waiting_end]
    
    # Create pagination object for waiting
    waiting_pages = (waiting_total + per_page - 1) // per_page if waiting_total > 0 else 1
    waiting_pagination = type('Pagination', (), {
        'page': waiting_page,
        'per_page': per_page,
        'total': waiting_total,
        'pages': waiting_pages,
        'has_prev': waiting_page > 1,
        'has_next': waiting_end < waiting_total,
        'prev_num': waiting_page - 1 if waiting_page > 1 else None,
        'next_num': waiting_page + 1 if waiting_end < waiting_total else None
    })()
    
    # Paginate completed entries
    completed_total = len(completed_entries_list)
    completed_start = (completed_page - 1) * per_page
    completed_end = completed_start + per_page
    completed_entries = completed_entries_list[completed_start:completed_end]
    
    # Create pagination object for completed
    completed_pages = (completed_total + per_page - 1) // per_page if completed_total > 0 else 1
    completed_pagination = type('Pagination', (), {
        'page': completed_page,
        'per_page': per_page,
        'total': completed_total,
        'pages': completed_pages,
        'has_prev': completed_page > 1,
        'has_next': completed_end < completed_total,
        'prev_num': completed_page - 1 if completed_page > 1 else None,
        'next_num': completed_page + 1 if completed_end < completed_total else None
    })()
    
    return render_template('admin/order_comments.html', 
                         waiting_entries=waiting_entries,
                         completed_entries=completed_entries,
                         waiting_pagination=waiting_pagination,
                         completed_pagination=completed_pagination)

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


# Payment success route - Note: This route should verify payment before clearing cart
# Currently, ZarinPal redirects to /zarinpal/verify which handles payment verification
# This route is kept for backward compatibility but should not clear cart without verification
@app.route('/payment_success')
@login_required
def payment_success():
    # DO NOT clear cart here - payment must be verified first
    # This route should redirect to zarinpal/verify for proper payment verification
    # Cart will only be cleared after successful payment verification in zarinpal/verify route
    flash_translated('payment_verification_required', 'warning')
    return redirect(url_for('index'))

@app.route('/payment_failure')
@login_required
def payment_failure():
    # Wallet feature removed
    flash_translated('order_payment_failed', 'error')
    return redirect(url_for('cart'))

# Wallet feature removed

@app.route('/process_order', methods=['POST'])
@login_required
def process_order():
    try:
        # Get cart items
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        
        if not cart_items:
            flash_translated('cart_empty', 'error')
            return redirect(url_for('cart'))
        
        # Calculate subtotal without discounts
        subtotal = sum(item.product.price * item.quantity for item in cart_items)
        
        # Get form data
        delivery_type = request.form.get('delivery_type')
        payment_method = 'online'  # Payment method is always online
        
        # Calculate delivery fee
        delivery_fee = 0.0
        if delivery_type == 'delivery':
            delivery_fee = max(20000, subtotal * 0.05)
        
        # Calculate total
        total = subtotal + delivery_fee
        
        # Validate delivery type
        if delivery_type == 'pickup':
            store_location_id = request.form.get('store_location_id')
            if not store_location_id:
                flash_translated('please_select_store_location', 'error')
                return redirect(url_for('cart'))
        else:  # delivery
            address_id = request.form.get('delivery_address_id')
            if not address_id:
                flash_translated('please_select_delivery_address', 'error')
                return redirect(url_for('cart'))
        
            # Store order details in session for payment success
            session['order_total'] = total
            session['payment_method'] = payment_method
            session['delivery_type'] = delivery_type
            session['store_location_id'] = store_location_id if delivery_type == 'pickup' else None
            session['address_id'] = address_id if delivery_type == 'delivery' else None
            session['order_description'] = request.form.get('order_description', '').strip()

            # Create ZarinPal payment request
            description = f"Order payment for {current_user.username}"
            callback_url = url_for('zarinpal_verify', _external=True)
            
            # Convert total to integer (ZarinPal expects amount in Tomans)
            amount_in_tomans = int(total)
            
            status, authority = create_payment_request(
                amount=amount_in_tomans,
                description=description,
            email=None,
                callback_url=callback_url
            )
            
            if status == 100 and authority:
                # Store authority and amount in session for verification
                session['zarinpal_authority'] = authority
                session['zarinpal_amount'] = amount_in_tomans
                return redirect(f'https://www.zarinpal.com/pg/StartPay/{authority}')
            else:
                flash_translated('payment_gateway_error', 'error')
                return redirect(url_for('cart'))
            
    except Exception as e:
        db.session.rollback()
        print(f"Error processing order: {str(e)}")
        flash_translated('error_processing_order', 'error')
        return redirect(url_for('cart'))

@app.route('/zarinpal/verify')
@login_required
def zarinpal_verify():
    try:
        authority = request.args.get('Authority')
        status = request.args.get('Status')
        
        # Verify that this is the same authority we stored
        if authority != session.get('zarinpal_authority'):
            flash_translated('invalid_payment_authority', 'error')
            return redirect(url_for('cart'))
        
        if status == 'OK':
            # Get the exact amount that was used in the payment request
            amount = session.get('zarinpal_amount')
            if not amount:
                flash_translated('payment_amount_not_found', 'error')
                return redirect(url_for('cart'))
            
            # Verify payment with ZarinPal using the exact same amount
            ref_id, verify_status = verify_payment(
                authority=authority,
                amount=amount  # Use the exact amount from the payment request
            )
            
            # Check if payment verification was successful (status 100)
            if verify_status == 100 and ref_id:
                try:
                    # Create order and order items from cart
                    order = Order(
                        user_id=current_user.id,
                        total_amount=session['order_total'],
                        delivery_fee=20000 if session['delivery_type'] == 'delivery' else 0,
                        status='pending_approval',  # Set initial status to pending_approval
                        payment_method='online',
                        delivery_type=session['delivery_type'],
                        store_location_id=session.get('store_location_id'),
                        address_id=session.get('address_id'),
                        description=session.get('order_description', '')
                    )
                    db.session.add(order)
                    db.session.flush()  # Get order ID
                    
                    # Get cart items BEFORE creating order - preserve cart if order creation fails
                    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
                    
                    # Verify cart items still exist before proceeding
                    if not cart_items:
                        db.session.rollback()
                        flash_translated('cart_empty', 'error')
                        return redirect(url_for('cart'))
                    
                    # Add order items from cart
                    for item in cart_items:
                        order_item = OrderItem(
                            order_id=order.id,
                            product_id=item.product_id,
                            quantity=item.quantity,
                            price=item.product.price  # Use base price without discount
                        )
                        db.session.add(order_item)
                        
                        # Update product stock
                        item.product.stock -= item.quantity
                        
                    # Commit order and order items first
                    db.session.commit()
                    
                    # Only clear cart AFTER successful commit - ensures cart remains if commit fails
                    for item in cart_items:
                        db.session.delete(item)
                    db.session.commit()
                    
                    # Clear session data
                    session.pop('order_total', None)
                    session.pop('payment_method', None)
                    session.pop('delivery_type', None)
                    session.pop('store_location_id', None)
                    session.pop('address_id', None)
                    session.pop('order_description', None)
                    session.pop('zarinpal_authority', None)
                    session.pop('zarinpal_amount', None)  # Clear the stored amount
                    
                    flash_translated('payment_successful', 'success')
                    return redirect(url_for('order_status', order_id=order.id))
                    
                except Exception as e:
                    db.session.rollback()
                    print(f"Error creating order: {str(e)}")
                    flash_translated('error_creating_order', 'error')
                    return redirect(url_for('cart'))
            else:
                print(f"Payment verification failed. Status: {verify_status}, Ref ID: {ref_id}")
                flash_translated('payment_verification_failed', 'error')
                return redirect(url_for('cart'))
        else:
            # Payment was cancelled by user - DO NOT clear cart
            flash_translated('payment_cancelled', 'error')
            # Cart remains intact for user to retry
            return redirect(url_for('cart'))
            
    except Exception as e:
        db.session.rollback()
        print(f"Error verifying payment: {str(e)}")
        flash_translated('error_verifying_payment', 'error')
        # Cart remains intact on error - user can retry
        return redirect(url_for('cart'))

if __name__ == '__main__':
    with app.app_context():
        init_db()  # Initialize the database
    app.run(debug=True, port=80, host='0.0.0.0') 