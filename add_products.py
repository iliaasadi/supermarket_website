from app import app, db
from models import Product

def add_products():
    # تنقلات (Snacks)
    snacks = [
        {"name": "چیپس", "category": "تنقلات", "price": 15000, "stock": 100, "description": "چیپس سیب زمینی ترد و خوشمزه"},
        {"name": "پفک", "category": "تنقلات", "price": 12000, "stock": 100, "description": "پفک پنیری با طعم عالی"},
        {"name": "پفیلا", "category": "تنقلات", "price": 13000, "stock": 100, "description": "پفیلا با طعم پنیر"},
        {"name": "چیپلت", "category": "تنقلات", "price": 14000, "stock": 100, "description": "چیپلت با طعم پنیر"},
        {"name": "کرانچی", "category": "تنقلات", "price": 16000, "stock": 100, "description": "کرانچی با طعم پنیر"},
        {"name": "لواشک", "category": "تنقلات", "price": 8000, "stock": 100, "description": "لواشک خانگی"},
        {"name": "شکلات", "category": "تنقلات", "price": 20000, "stock": 100, "description": "شکلات شیری"},
        {"name": "پاستیل", "category": "تنقلات", "price": 10000, "stock": 100, "description": "پاستیل میوه‌ای"},
    ]

    # دخانیات (Tobacco)
    tobacco = [
        {"name": "سیگار", "category": "دخانیات", "price": 25000, "stock": 50, "description": "سیگار خارجی"},
        {"name": "پاد", "category": "دخانیات", "price": 30000, "stock": 50, "description": "پاد خارجی"},
    ]

    # لبنیات (Dairy)
    dairy = [
        {"name": "ماست", "category": "لبنیات", "price": 15000, "stock": 50, "description": "ماست محلی"},
        {"name": "شیر", "category": "لبنیات", "price": 20000, "stock": 50, "description": "شیر تازه"},
        {"name": "کره", "category": "لبنیات", "price": 35000, "stock": 30, "description": "کره محلی"},
        {"name": "پنیر", "category": "لبنیات", "price": 40000, "stock": 40, "description": "پنیر محلی"},
        {"name": "دوغ محلی", "category": "لبنیات", "price": 12000, "stock": 60, "description": "دوغ محلی تازه"},
    ]

    # نوشیدنی (Beverages)
    beverages = [
        {"name": "آبمیوه پرتغال", "category": "نوشیدنی", "price": 18000, "stock": 80, "description": "آبمیوه پرتغال طبیعی"},
        {"name": "آبمیوه لیمو", "category": "نوشیدنی", "price": 16000, "stock": 80, "description": "آبمیوه لیمو طبیعی"},
        {"name": "آبمیوه البالو", "category": "نوشیدنی", "price": 17000, "stock": 80, "description": "آبمیوه البالو طبیعی"},
    ]

    # میوه و سبزیجات (Fruits and Vegetables)
    fruits = [
        {"name": "سبزی", "category": "میوه و سبزیجات", "price": 10000, "stock": 100, "description": "سبزی تازه"},
        {"name": "هلو", "category": "میوه و سبزیجات", "price": 25000, "stock": 50, "description": "هلو تازه"},
        {"name": "پرتغال", "category": "میوه و سبزیجات", "price": 20000, "stock": 60, "description": "پرتغال تازه"},
        {"name": "نارنگی", "category": "میوه و سبزیجات", "price": 18000, "stock": 70, "description": "نارنگی تازه"},
        {"name": "توت فرنگی", "category": "میوه و سبزیجات", "price": 35000, "stock": 40, "description": "توت فرنگی تازه"},
        {"name": "گیلاس", "category": "میوه و سبزیجات", "price": 30000, "stock": 45, "description": "گیلاس تازه"},
    ]

    # Combine all products
    all_products = snacks + tobacco + dairy + beverages + fruits

    # Add products to database
    with app.app_context():
        for product_data in all_products:
            # Check if product already exists
            existing_product = Product.query.filter_by(
                name=product_data["name"],
                category=product_data["category"]
            ).first()
            
            if not existing_product:
                product = Product(
                    name=product_data["name"],
                    category=product_data["category"],
                    price=product_data["price"],
                    stock=product_data["stock"],
                    description=product_data["description"],
                    image_url=f"/static/images/products/{product_data['category']}/{product_data['name']}.jpg"
                )
                db.session.add(product)
                print(f"Added new product: {product_data['name']} in category: {product_data['category']}")
            else:
                print(f"Product already exists: {product_data['name']} in category: {product_data['category']}")
        
        try:
            db.session.commit()
            print("Products added successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error adding products: {str(e)}")

def add_five_products():
    products = [
        {"name": "کیک وانیلی", "category": "شیرینی", "price": 25000, "stock": 40, "description": "کیک وانیلی تازه و خوشمزه", "image_url": "https://upload.wikimedia.org/wikipedia/commons/0/04/Pound_layer_cake.jpg"},
        {"name": "آب معدنی", "category": "نوشیدنی", "price": 5000, "stock": 100, "description": "آب معدنی خنک و سالم", "image_url": "https://upload.wikimedia.org/wikipedia/commons/6/6b/Bottled_Water.jpg"},
        {"name": "پنیر پیتزا", "category": "لبنیات", "price": 60000, "stock": 30, "description": "پنیر پیتزا مخصوص", "image_url": "https://upload.wikimedia.org/wikipedia/commons/2/2c/White_cheese.jpg"},
        {"name": "سیب سبز", "category": "میوه", "price": 30000, "stock": 60, "description": "سیب سبز تازه و آبدار", "image_url": "https://upload.wikimedia.org/wikipedia/commons/1/15/Granny_smith_and_cross_section.jpg"},
        {"name": "سس کچاپ", "category": "چاشنی", "price": 12000, "stock": 80, "description": "سس کچاپ خوش طعم", "image_url": "https://upload.wikimedia.org/wikipedia/commons/0/09/Tomato_ketchup.jpg"},
    ]
    with app.app_context():
        for p in products:
            existing = Product.query.filter_by(name=p["name"], category=p["category"]).first()
            if not existing:
                product = Product(**p)
                db.session.add(product)
                print(f"Added: {p['name']} ({p['category']})")
            else:
                print(f"Already exists: {p['name']} ({p['category']})")
        try:
            db.session.commit()
            print("5 products added successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    add_products()
    add_five_products() 