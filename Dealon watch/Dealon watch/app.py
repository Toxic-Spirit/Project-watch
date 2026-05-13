# app.py
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from sqlalchemy import func
import secrets

from app_config import Config

UPLOAD_FOLDER = os.path.join('static', 'product_images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app = Flask(__name__)
app.config.from_object(Config)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Database Models ---

class User(db.Model):
    user_id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username          = db.Column(db.String(80), unique=True, nullable=False)
    email             = db.Column(db.String(120), unique=True, nullable=False)
    password_hash     = db.Column(db.String(128), nullable=False)
    user_type         = db.Column(db.String(20), nullable=False)
    is_approved       = db.Column(db.Integer, default=1)
    rejection_reason  = db.Column(db.Text, nullable=True)
    gst_no            = db.Column(db.String(20), nullable=True)
    aadhar_no         = db.Column(db.String(20), nullable=True)
    bank_ac_no        = db.Column(db.String(30), nullable=True)
    products  = db.relationship('Product', backref='seller', lazy=True)
    tokens    = db.relationship('Token', backref='user', lazy=True, cascade='all, delete-orphan')
    cart      = db.relationship('Cart', backref='user', uselist=False, cascade='all, delete-orphan')

class Category(db.Model):
    category_id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name               = db.Column(db.String(100), unique=False, nullable=False)
    parent_category_id = db.Column(db.Integer, db.ForeignKey('category.category_id'), nullable=True)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    product_id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    seller_id        = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    name             = db.Column(db.String(255), nullable=False)
    description      = db.Column(db.Text, nullable=False)
    price            = db.Column(db.Numeric(10, 2), nullable=False)
    category_id      = db.Column(db.Integer, db.ForeignKey('category.category_id'), nullable=False)
    brand            = db.Column(db.String(100))
    stock            = db.Column(db.Integer, default=0)
    max_purchase_qty = db.Column(db.Integer, default=10)
    images      = db.relationship('ProductImage', backref='product', lazy=True, cascade='all, delete-orphan')
    cart_items  = db.relationship('CartItem', backref='product', lazy=True, cascade='all, delete-orphan')
    reviews     = db.relationship('Review', backref='product', lazy=True, cascade='all, delete-orphan')
    order_items = db.relationship('OrderItem', backref='product', lazy=True)

class ProductImage(db.Model):
    image_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.product_id', ondelete='CASCADE'), nullable=False)
    image_url  = db.Column(db.String(255), nullable=False)
    is_main    = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)

class Order(db.Model):
    order_id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    total          = db.Column(db.Numeric(10, 2), nullable=False)
    status         = db.Column(db.String(50), default='Pending')
    order_date     = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50), default='card')
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    item_id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id          = db.Column(db.Integer, db.ForeignKey('order.order_id', ondelete='CASCADE'), nullable=False)
    product_id        = db.Column(db.Integer, db.ForeignKey('product.product_id', ondelete='SET NULL'), nullable=True)
    quantity          = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Numeric(10, 2), nullable=False)

class Cart(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.user_id'), primary_key=True)
    items   = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')

class CartItem(db.Model):
    cart_item_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('cart.user_id'), nullable=False)
    product_id   = db.Column(db.Integer, db.ForeignKey('product.product_id', ondelete='CASCADE'), nullable=False)
    quantity     = db.Column(db.Integer, nullable=False)

class Review(db.Model):
    review_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    product_id  = db.Column(db.Integer, db.ForeignKey('product.product_id', ondelete='CASCADE'), nullable=False)
    rating      = db.Column(db.Integer, nullable=False)
    comment     = db.Column(db.Text)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

class Token(db.Model):
    token_id   = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.user_id'), nullable=False)
    token_hash = db.Column(db.String(256), unique=True, nullable=False)
    expiration = db.Column(db.DateTime, nullable=False)


# --- Helper Functions ---

@app.context_processor
def inject_global_data():
    categories = Category.query.all()
    category_tree = {}
    for category in categories:
        if category.parent_category_id is None:
            category_tree[category] = []
    for category in categories:
        if category.parent_category_id is not None:
            for parent in category_tree:
                if parent.category_id == category.parent_category_id:
                    category_tree[parent].append(category)
                    break
    return dict(ROLES=app.config['ROLES'], NAV_CATEGORIES=category_tree)

def role_required(role):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_type' not in session or session['user_type'] != role:
                flash("Access denied.", 'danger')
                return redirect(url_for('login', user_role='customer'))
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.before_request
def check_remember_me():
    if 'user_id' not in session and request.cookies.get('remember_token'):
        token = request.cookies.get('remember_token')
        token_record = Token.query.filter(Token.token_hash == token).first()
        if token_record and token_record.expiration > datetime.utcnow():
            user = User.query.get(token_record.user_id)
            if user:
                session['user_id']   = user.user_id
                session['username']  = user.username
                session['user_type'] = user.user_type
        elif token_record:
            db.session.delete(token_record)
            db.session.commit()

def create_initial_admin():
    with app.app_context():
        if db.session.query(User).filter(User.user_type == app.config['ROLES']['ADMIN']).count() == 0:
            hashed_password = bcrypt.generate_password_hash("AdminSecurePass123").decode('utf-8')
            admin = User(username="DeaLonAdmin", email="admin@dealon.com",
                         password_hash=hashed_password, user_type=app.config['ROLES']['ADMIN'],
                         is_approved=1)
            db.session.add(admin)
            db.session.commit()
            print("--- Initial Admin account created: DeaLonAdmin ---")

with app.app_context():
    db.create_all()
    create_initial_admin()


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    products = Product.query.all()
    products_with_images = []
    for product in products:
        main_image = ProductImage.query.filter_by(product_id=product.product_id, is_main=True).first()
        products_with_images.append({
            'product': product,
            'image_url': main_image.image_url if main_image else '/static/product_images/placeholder.jpg'
        })

    # ── Recently Viewed ──
    recently_viewed_ids = session.get('recently_viewed', [])
    recently_viewed = []
    for pid in recently_viewed_ids:
        product = Product.query.get(pid)
        if product:
            main_image = ProductImage.query.filter_by(product_id=pid, is_main=True).first()
            recently_viewed.append({
                'product': product,
                'image_url': main_image.image_url if main_image else '/static/product_images/placeholder.jpg'
            })

    return render_template('index.html', title='Home',
                           products_with_images=products_with_images,
                           recently_viewed=recently_viewed)

@app.route('/search')
def search():
    query       = request.args.get('q', '')
    min_price   = request.args.get('min_price')
    max_price   = request.args.get('max_price')
    brand_filter = request.args.get('brand')
    base_query = Product.query.filter(
        Product.name.like(f"%{query}%") | Product.brand.like(f"%{query}%")
    )
    if min_price and min_price.replace('.', '', 1).isdigit():
        base_query = base_query.filter(Product.price >= float(min_price))
    if max_price and max_price.replace('.', '', 1).isdigit():
        base_query = base_query.filter(Product.price <= float(max_price))
    if brand_filter:
        base_query = base_query.filter(Product.brand == brand_filter)
    products = base_query.all()
    products_with_images = []
    for product in products:
        main_image = ProductImage.query.filter_by(product_id=product.product_id, is_main=True).first()
        products_with_images.append({
            'product': product,
            'image_url': main_image.image_url if main_image else '/static/product_images/placeholder.jpg'
        })
    available_brands = db.session.query(Product.brand).filter(
        Product.name.like(f"%{query}%") | Product.brand.like(f"%{query}%")
    ).distinct().order_by(Product.brand).all()
    brand_list = [brand[0] for brand in available_brands if brand[0]]
    return render_template('search_results.html', title=f"Search for '{query}'",
                           query=query, products_with_images=products_with_images,
                           available_brands=brand_list, current_min_price=min_price,
                           current_max_price=max_price, current_brand=brand_filter)

@app.route('/about')
def about_us():
    return render_template('about_us.html', title='About Us')

@app.route('/contact')
def contact_us():
    return render_template('contact_us.html', title='Contact Us')

@app.route('/customer-service')
def customer_service():
    return render_template('customer_service.html', title='Customer Service')

@app.route('/terms-and-conditions')
def terms_and_conditions():
    return render_template('terms_and_conditions.html', title='Terms & Conditions')

@app.route('/track')
def order_tracking():
    if session.get('user_id') and session.get('user_type') == Config.ROLES['CUSTOMER']:
        orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.order_date.desc()).all()
        return render_template('order_tracking.html', title='My Orders', orders=orders)
    flash("Please log in to track your orders.", 'info')
    return redirect(url_for('login', user_role='customer'))

@app.route('/privacy-notice')
def privacy_notice():
    return render_template('privacy_notice.html', title='Privacy Notice')

@app.route('/ads-policy')
def ads_policy():
    return render_template('interest_based_ads.html', title='Interest-Based Ads')

@app.route('/category/<string:category_name>')
def category_view(category_name):
    categories = Category.query.filter_by(name=category_name).all()
    category_ids = [c.category_id for c in categories]
    products = Product.query.filter(Product.category_id.in_(category_ids)).all() if categories else []
    products_with_images = []
    for product in products:
        main_image = ProductImage.query.filter_by(product_id=product.product_id, is_main=True).first()
        products_with_images.append({
            'product': product,
            'image_url': main_image.image_url if main_image else '/static/product_images/placeholder.jpg'
        })
    return render_template('category_page.html', title=category_name,
                           category_name=category_name, products_with_images=products_with_images)

# ─── Profile ─────────────────────────────────────────────────────────────────

@app.route('/profile')
def my_profile():
    if not session.get('user_id'):
        return redirect(url_for('login', user_role='customer'))
    user_type = session.get('user_type')
    if user_type == Config.ROLES['ADMIN']:
        return redirect(url_for('admin_dashboard'))
    elif user_type == Config.ROLES['SELLER']:
        return redirect(url_for('seller_dashboard'))
    else:
        return redirect(url_for('customer_profile'))

@app.route('/customer/profile')
@role_required(Config.ROLES['CUSTOMER'])
def customer_profile():
    return render_template('customer_profile.html', title='My Profile')


# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
@role_required(Config.ROLES['ADMIN'])
def admin_dashboard():
    all_products = Product.query.all()

    # Seller groups
    pending_sellers  = User.query.filter_by(user_type=Config.ROLES['SELLER'], is_approved=0).all()
    approved_sellers = User.query.filter_by(user_type=Config.ROLES['SELLER'], is_approved=1).all()
    rejected_sellers = User.query.filter_by(user_type=Config.ROLES['SELLER'], is_approved=2).all()

    # ── Earnings calculations ──
    # Only count non-cancelled orders
    valid_orders = Order.query.filter(Order.status != 'Cancelled').all()
    total_orders = len(valid_orders)

    # Total sales = sum of all order_item (price * qty) for non-cancelled orders
    valid_order_ids = [o.order_id for o in valid_orders]

    if valid_order_ids:
        items = db.session.query(OrderItem).filter(
            OrderItem.order_id.in_(valid_order_ids)
        ).all()
        total_sales = sum(float(i.price_at_purchase) * i.quantity for i in items)
    else:
        total_sales = 0.0

    admin_total  = round(total_sales * 0.20, 2)
    seller_total = round(total_sales * 0.80, 2)

    # Earnings per seller
    seller_earnings = []
    all_sellers = User.query.filter_by(user_type=Config.ROLES['SELLER']).all()
    for seller in all_sellers:
        seller_product_ids = [p.product_id for p in seller.products]
        if not seller_product_ids:
            continue
        seller_items = [i for i in items if i.product_id in seller_product_ids] if valid_order_ids else []
        if not seller_items:
            continue
        s_total = sum(float(i.price_at_purchase) * i.quantity for i in seller_items)
        seller_earnings.append({
            'username':     seller.username,
            'email':        seller.email,
            'items_sold':   sum(i.quantity for i in seller_items),
            'total_sales':  s_total,
            'admin_share':  round(s_total * 0.20, 2),
            'seller_payout': round(s_total * 0.80, 2),
        })

    # Recent orders (last 20)
    recent_orders = db.session.query(Order, User.username).join(
        User, Order.user_id == User.user_id
    ).order_by(Order.order_date.desc()).limit(20).all()

    recent_orders_data = []
    for order, username in recent_orders:
        recent_orders_data.append({
            'order_id':       order.order_id,
            'username':       username,
            'order_date':     order.order_date,
            'payment_method': order.payment_method,
            'status':         order.status,
            'total':          order.total,
        })

    return render_template('admin_dashboard.html', title='Admin Panel',
                           products=all_products,
                           pending_sellers=pending_sellers,
                           approved_sellers=approved_sellers,
                           rejected_sellers=rejected_sellers,
                           total_sales=total_sales,
                           admin_total=admin_total,
                           seller_total=seller_total,
                           total_orders=total_orders,
                           seller_earnings=seller_earnings,
                           recent_orders=recent_orders_data)

@app.route('/admin/approve-seller/<int:seller_id>', methods=['POST'])
@role_required(Config.ROLES['ADMIN'])
def admin_approve_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    seller.is_approved = 1
    seller.rejection_reason = None
    db.session.commit()
    flash(f"Seller '{seller.username}' approved. They can now log in.", 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-seller/<int:seller_id>', methods=['POST'])
@role_required(Config.ROLES['ADMIN'])
def admin_reject_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    reason = request.form.get('rejection_reason', '').strip()
    if not reason:
        flash("Please provide a rejection reason.", 'warning')
        return redirect(url_for('admin_dashboard'))
    seller.is_approved = 2
    seller.rejection_reason = reason
    db.session.commit()
    flash(f"Seller '{seller.username}' rejected.", 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/revoke-seller/<int:seller_id>', methods=['POST'])
@role_required(Config.ROLES['ADMIN'])
def admin_revoke_seller(seller_id):
    seller = User.query.get_or_404(seller_id)
    seller.is_approved = 0
    db.session.commit()
    flash(f"Seller '{seller.username}' approval revoked.", 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-product/<int:product_id>')
@role_required(Config.ROLES['ADMIN'])
def admin_delete_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.", 'danger')
        return redirect(url_for('admin_dashboard'))
    product_name = product.name
    try:
        db.session.delete(product)
        db.session.commit()
        flash(f"Product '{product_name}' removed.", 'success')
    except Exception as e:
        db.session.rollback()
        flash("Error during deletion.", 'danger')
    return redirect(url_for('admin_dashboard'))


# ─── Seller Routes ────────────────────────────────────────────────────────────

@app.route('/seller/dashboard')
@role_required(Config.ROLES['SELLER'])
def seller_dashboard():
    seller_id = session['user_id']
    seller_products = Product.query.filter_by(seller_id=seller_id).all()
    seller_product_ids = [p.product_id for p in seller_products]

    # ── Sales analytics ──
    # Only non-cancelled orders
    valid_order_ids = [o.order_id for o in Order.query.filter(Order.status != 'Cancelled').all()]

    if seller_product_ids and valid_order_ids:
        sold_items = db.session.query(OrderItem).filter(
            OrderItem.product_id.in_(seller_product_ids),
            OrderItem.order_id.in_(valid_order_ids)
        ).all()
    else:
        sold_items = []

    total_revenue   = sum(float(i.price_at_purchase) * i.quantity for i in sold_items)
    admin_commission = round(total_revenue * 0.20, 2)
    seller_earnings  = round(total_revenue * 0.80, 2)
    total_sold       = sum(i.quantity for i in sold_items)

    # Sales grouped by product
    product_sales = []
    for product in seller_products:
        p_items = [i for i in sold_items if i.product_id == product.product_id]
        if not p_items:
            continue
        units   = sum(i.quantity for i in p_items)
        revenue = sum(float(i.price_at_purchase) * i.quantity for i in p_items)
        product_sales.append({
            'name':         product.name,
            'brand':        product.brand,
            'units_sold':   units,
            'unit_price':   float(product.price),
            'total_revenue': revenue,
            'seller_cut':   round(revenue * 0.80, 2),
            'admin_cut':    round(revenue * 0.20, 2),
        })
    product_sales.sort(key=lambda x: x['units_sold'], reverse=True)

    # Recent orders containing seller's products
    seller_orders = []
    if seller_product_ids and valid_order_ids:
        results = db.session.query(
            OrderItem, Order, Product
        ).join(
            Order, OrderItem.order_id == Order.order_id
        ).join(
            Product, OrderItem.product_id == Product.product_id
        ).filter(
            OrderItem.product_id.in_(seller_product_ids),
            OrderItem.order_id.in_(valid_order_ids)
        ).order_by(Order.order_date.desc()).limit(20).all()

        for item, order, product in results:
            seller_orders.append({
                'order_id':         order.order_id,
                'product_name':     product.name,
                'quantity':         item.quantity,
                'price_at_purchase': item.price_at_purchase,
                'line_total':       float(item.price_at_purchase) * item.quantity,
                'order_date':       order.order_date,
                'status':           order.status,
            })

    return render_template('seller_dashboard.html', title='Seller Panel',
                           products=seller_products,
                           total_revenue=total_revenue,
                           admin_commission=admin_commission,
                           seller_earnings=seller_earnings,
                           total_sold=total_sold,
                           product_sales=product_sales,
                           seller_orders=seller_orders)

@app.route('/seller/add-product', methods=['GET', 'POST'])
@role_required(Config.ROLES['SELLER'])
def add_product():
    categories = Category.query.all()
    if request.method == 'POST':
        name        = request.form.get('name')
        price       = request.form.get('price')
        description = request.form.get('description')
        category_id = request.form.get('category')
        brand       = request.form.get('brand')
        stock       = request.form.get('stock')
        image_files = request.files.getlist('images')
        category_obj  = Category.query.get(category_id)
        category_name = category_obj.name.lower() if category_obj else ""
        if 'mobile' in category_name or 'laptop' in category_name:
         max_qty = 1
        elif 'furniture' in category_name:
            max_qty = 4
        elif 'watch' in category_name:
            max_qty = 2
        elif 'perfume' in category_name:
            max_qty = 7
        else:
            max_qty = 2
        new_product = Product(seller_id=session['user_id'], name=name, price=price,
                              description=description, category_id=category_id,
                              brand=brand, stock=stock, max_purchase_qty=max_qty)
        db.session.add(new_product)
        db.session.commit()
        product_id = new_product.product_id
        main_image_set = False
        for i, file in enumerate(image_files):
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{product_id}_{i}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                is_main = not main_image_set
                if is_main:
                    main_image_set = True
                new_image = ProductImage(product_id=product_id,
                                         image_url=f'/{UPLOAD_FOLDER}/{filename}',
                                         is_main=is_main, sort_order=i)
                db.session.add(new_image)
        db.session.commit()
        flash(f'Product "{name}" added successfully.', 'success')
        return redirect(url_for('seller_dashboard'))
    return render_template('add_product.html', title='Add New Product', categories=categories)

@app.route('/seller/edit-product/<int:product_id>', methods=['GET', 'POST'])
@role_required(Config.ROLES['SELLER'])
def edit_product(product_id):
    product    = Product.query.filter_by(product_id=product_id, seller_id=session['user_id']).first_or_404()
    categories = Category.query.all()
    if request.method == 'POST':
        product.name        = request.form.get('name')
        product.price       = request.form.get('price')
        product.description = request.form.get('description')
        product.category_id = request.form.get('category')
        product.brand       = request.form.get('brand')
        product.stock       = request.form.get('stock')
        db.session.commit()
        flash(f'Product "{product.name}" updated.', 'success')
        return redirect(url_for('seller_dashboard'))
    return render_template('edit_product.html', title=f'Edit {product.name}',
                           product=product, categories=categories)

@app.route('/seller/delete-product/<int:product_id>')
@role_required(Config.ROLES['SELLER'])
def delete_product(product_id):
    product = Product.query.filter_by(product_id=product_id, seller_id=session['user_id']).first()
    if not product:
        flash("Product not found or no permission.", 'danger')
        return redirect(url_for('seller_dashboard'))
    try:
        db.session.delete(product)
        db.session.commit()
        flash(f"Product '{product.name}' removed.", 'success')
    except Exception as e:
        db.session.rollback()
        flash("Error during deletion.", 'danger')
    return redirect(url_for('seller_dashboard'))


# ─── Cart & Checkout ──────────────────────────────────────────────────────────

@app.route('/cart')
@role_required(Config.ROLES['CUSTOMER'])
def view_cart():
    user_id = session['user_id']
    total_price = 0
    cart_items_records = CartItem.query.filter_by(user_id=user_id).all()
    products_in_cart = []
    for item_record in cart_items_records:
        product = Product.query.get(item_record.product_id)
        if product:
            item_total = item_record.quantity * float(product.price)
            total_price += item_total
            products_in_cart.append({'item': item_record, 'product': product, 'item_total': item_total})
    return render_template('cart.html', title='Your Shopping Cart',
                           cart_items=products_in_cart, total_price=total_price)

@app.route('/cart/add/<int:product_id>', methods=['POST'])
@role_required(Config.ROLES['CUSTOMER'])
def add_to_cart(product_id):
    user_id  = session['user_id']
    quantity = int(request.form.get('quantity', 1))
    product  = Product.query.get_or_404(product_id)
    if product.stock == 0:
        flash(f'Sorry, "{product.name}" is out of stock.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))
    if quantity > product.stock:
        flash(f'Only {product.stock} units available.', 'warning')
        return redirect(url_for('product_detail', product_id=product_id))
    if quantity > product.max_purchase_qty:
        flash(f"Max purchase limit is {product.max_purchase_qty}.", 'warning')
        return redirect(url_for('product_detail', product_id=product_id))
    cart = Cart.query.get(user_id)
    if not cart:
        cart = Cart(user_id=user_id)
        db.session.add(cart)
    cart_item = CartItem.query.filter_by(user_id=user_id, product_id=product_id).first()
    if cart_item:
        new_quantity = cart_item.quantity + quantity
        if new_quantity > product.max_purchase_qty or new_quantity > product.stock:
            flash('Cannot add more. Limit or stock reached.', 'warning')
            return redirect(url_for('product_detail', product_id=product_id))
        cart_item.quantity = new_quantity
    else:
        cart_item = CartItem(user_id=user_id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    db.session.commit()
    flash(f"{product.name} (x{quantity}) added to cart!", 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart/remove/<int:product_id>')
@role_required(Config.ROLES['CUSTOMER'])
def remove_from_cart(product_id):
    user_id   = session['user_id']
    cart_item = CartItem.query.filter_by(user_id=user_id, product_id=product_id).first()
    if cart_item:
        db.session.delete(cart_item)
        db.session.commit()
        flash("Item removed from cart.", 'info')
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@role_required(Config.ROLES['CUSTOMER'])
def checkout():
    user_id = session['user_id']
    cart_items_records = CartItem.query.filter_by(user_id=user_id).all()
    if not cart_items_records:
        flash("Your cart is empty.", 'warning')
        return redirect(url_for('view_cart'))
    products_in_cart = []
    total_price = 0
    for item_record in cart_items_records:
        product = Product.query.get(item_record.product_id)
        if product:
            item_total = item_record.quantity * float(product.price)
            total_price += item_total
            products_in_cart.append({'item': item_record, 'product': product, 'item_total': item_total})
    if request.method == 'GET':
        return render_template('checkout.html', title='Checkout',
                               cart_items=products_in_cart, total_price=total_price)
    if request.method == 'POST':
        payment_method = request.form.get('payment_method', 'card')
        try:
            for item_data in products_in_cart:
                product = item_data['product']
                if product.stock < item_data['item'].quantity:
                    flash(f'Only {product.stock} units of "{product.name}" available.', 'danger')
                    return redirect(url_for('view_cart'))
            new_order = Order(user_id=user_id, total=total_price,
                              status='Confirmed', payment_method=payment_method)
            db.session.add(new_order)
            db.session.flush()
            for item_data in products_in_cart:
                product  = item_data['product']
                quantity = item_data['item'].quantity
                order_item = OrderItem(order_id=new_order.order_id,
                                       product_id=product.product_id,
                                       quantity=quantity,
                                       price_at_purchase=product.price)
                db.session.add(order_item)
                product.stock = product.stock - quantity
            for item_record in cart_items_records:
                db.session.delete(item_record)
            db.session.commit()
            flash(f"Order #{new_order.order_id} placed! Payment via {payment_method.upper()}.", 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            print(f"Checkout error: {e}")
            flash("Error during checkout. Please try again.", 'danger')
            return redirect(url_for('view_cart'))

@app.route('/cancel-order/<int:order_id>', methods=['POST'])
@role_required(Config.ROLES['CUSTOMER'])
def cancel_order(order_id):
    user_id = session['user_id']
    order   = Order.query.filter_by(order_id=order_id, user_id=user_id).first()
    if not order:
        flash("Order not found.", 'danger')
        return redirect(url_for('order_tracking'))
    if order.status not in ['Confirmed', 'Preparing']:
        flash(f"Order #{order_id} cannot be cancelled.", 'warning')
        return redirect(url_for('order_tracking'))
    try:
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock = product.stock + item.quantity
        order.status = 'Cancelled'
        db.session.commit()
        flash(f"Order #{order_id} cancelled. Refund in 7-10 business days.", 'success')
    except Exception as e:
        db.session.rollback()
        flash("Error cancelling order.", 'danger')
    return redirect(url_for('order_tracking'))

@app.route('/seller/update-order-status/<int:order_id>', methods=['POST'])
@role_required(Config.ROLES['SELLER'])
def update_order_status(order_id):
    new_status = request.form.get('status')

    allowed_statuses = ['Confirmed', 'Preparing', 'Shipped', 'Out for Delivery', 'Delivered']
    if new_status not in allowed_statuses:
        flash("Invalid status.", 'danger')
        return redirect(url_for('seller_dashboard'))

    # Find the order — verify it contains at least one product from this seller
    seller_product_ids = [p.product_id for p in Product.query.filter_by(seller_id=session['user_id']).all()]
    order = Order.query.get_or_404(order_id)

    order_product_ids = [item.product_id for item in order.items]
    if not any(pid in seller_product_ids for pid in order_product_ids):
        flash("You don't have permission to update this order.", 'danger')
        return redirect(url_for('seller_dashboard'))

    if order.status == 'Cancelled':
        flash("Cannot update a cancelled order.", 'warning')
        return redirect(url_for('seller_dashboard'))

    order.status = new_status
    db.session.commit()
    flash(f"Order #{order_id} status updated to '{new_status}'.", 'success')
    return redirect(url_for('seller_dashboard'))
# ─── Product Detail ───────────────────────────────────────────────────────────

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    reviews = Review.query.filter_by(product_id=product_id).order_by(Review.date_posted.desc()).all()

    # ── Recently Viewed Tracking ──
    recently_viewed = session.get('recently_viewed', [])
    if product_id in recently_viewed:
        recently_viewed.remove(product_id)
    recently_viewed.insert(0, product_id)   # add to front
    recently_viewed = recently_viewed[:6]   # keep only last 6
    session['recently_viewed'] = recently_viewed
    session.modified = True

    # Check if already reviewed
    already_reviewed = False
    if session.get('user_id') and session.get('user_type') == 'Customer':
        existing = Review.query.filter_by(
            user_id=session['user_id'],
            product_id=product_id
        ).first()
        already_reviewed = existing is not None

    return render_template('product_detail.html',
                           title=product.name,
                           product=product,
                           reviews=reviews,
                           already_reviewed=already_reviewed)

@app.route('/product/<int:product_id>/review', methods=['POST'])
@role_required(Config.ROLES['CUSTOMER'])
def submit_review(product_id):
    user_id = session['user_id']
    product = Product.query.get_or_404(product_id)

    # Check if already reviewed
    existing = Review.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing:
        flash("You have already reviewed this product.", 'info')
        return redirect(url_for('product_detail', product_id=product_id))

    rating  = request.form.get('rating')
    comment = request.form.get('comment', '').strip()

    if not rating:
        flash("Please select a star rating.", 'warning')
        return redirect(url_for('product_detail', product_id=product_id))

    try:
        new_review = Review(
            user_id=user_id,
            product_id=product_id,
            rating=int(rating),
            comment=comment if comment else None
        )
        db.session.add(new_review)
        db.session.commit()
        flash("Thank you for your review!", 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Review error: {e}")
        flash("Error submitting review. Please try again.", 'danger')

    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/buy-now/<int:product_id>')
@role_required(Config.ROLES['CUSTOMER'])
def buy_now(product_id):
    flash("Redirecting to checkout...", 'info')
    return redirect(url_for('checkout'))


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/signup/<user_role>', methods=['GET', 'POST'])
def signup(user_role):
    if 'user_id' in session:
        flash("You are already logged in.", 'info')
        return redirect(url_for('index'))
    role = user_role.capitalize()
    if role not in [Config.ROLES['CUSTOMER'], Config.ROLES['SELLER'], Config.ROLES['ADMIN']]:
        abort(404)
    if request.method == 'POST':
        username = request.form.get('username')
        email    = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or Email already exists.', 'danger')
            return redirect(url_for('signup', user_role=user_role))
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        try:
            is_approved = 0 if role == Config.ROLES['SELLER'] else 1
            new_user = User(username=username, email=email,
                            password_hash=hashed_password, user_type=role,
                            is_approved=is_approved)
            if role == Config.ROLES['SELLER']:
                new_user.gst_no     = request.form.get('gst_no', '').strip().upper()
                new_user.aadhar_no  = request.form.get('aadhar_no', '').strip()
                new_user.bank_ac_no = request.form.get('bank_ac_no', '').strip()
            db.session.add(new_user)
            db.session.flush()
            if role == Config.ROLES['CUSTOMER']:
                new_cart = Cart(user_id=new_user.user_id)
                db.session.add(new_cart)
            db.session.commit()
            if role == Config.ROLES['SELLER']:
                flash('Application submitted! You can login after admin approval.', 'success')
            else:
                flash(f'{role} account created. Please log in.', 'success')
            return redirect(url_for('login', user_role=user_role))
        except Exception as e:
            db.session.rollback()
            print(f"Signup error: {e}")
            flash("An error occurred during signup.", 'danger')
            return redirect(url_for('signup', user_role=user_role))
    return render_template('signup.html', role=role, title=f'{role} Signup')

@app.route('/login/<user_role>', methods=['GET', 'POST'])
def login(user_role):
    if 'user_id' in session:
        flash("You are already logged in.", 'info')
        return redirect(url_for('index'))
    role = user_role.capitalize()
    if request.method == 'POST':
        db.session.remove()
        identifier  = request.form.get('identifier')
        password    = request.form.get('password')
        remember_me = request.form.get('remember')
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            if user.user_type != role:
                flash(f"Your account is a {user.user_type}, not a {role}.", 'danger')
                return redirect(url_for('login', user_role=user_role))
            # Seller approval gate
            if user.user_type == Config.ROLES['SELLER']:
                if user.is_approved == 0:
                    return render_template('seller_pending.html', title='Approval Pending')
                elif user.is_approved == 2:
                    return render_template('seller_rejected.html', title='Account Rejected',
                                           reason=user.rejection_reason or 'No reason provided.')
            response = make_response(redirect(url_for('index')))
            session['user_id']   = user.user_id
            session['username']  = user.username
            session['user_type'] = user.user_type
            if remember_me:
                raw_token       = secrets.token_urlsafe(32)
                expiration_date = datetime.utcnow() + timedelta(days=30)
                Token.query.filter_by(user_id=user.user_id).delete()
                new_token = Token(user_id=user.user_id, token_hash=raw_token, expiration=expiration_date)
                db.session.add(new_token)
                response.set_cookie('remember_token', raw_token, expires=expiration_date, httponly=True)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash("Session setup failed. Try again.", 'warning')
                return redirect(url_for('login', user_role=user_role))
            flash(f'Welcome back, {user.username}!', 'success')
            if user.user_type == Config.ROLES['ADMIN']:
                response.headers['Location'] = url_for('admin_dashboard')
            elif user.user_type == Config.ROLES['SELLER']:
                response.headers['Location'] = url_for('seller_dashboard')
            else:
                response.headers['Location'] = url_for('index')
            return response
        else:
            flash('Login failed. Check your credentials.', 'danger')
    return render_template('login.html', role=role, title=f'{role} Login')

@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('index')))
    token = request.cookies.get('remember_token')
    if token:
        token_record = Token.query.filter_by(token_hash=token).first()
        if token_record:
            db.session.delete(token_record)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        response.set_cookie('remember_token', '', expires=0, httponly=True)
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('user_type', None)
    db.session.remove()
    flash('Logged out successfully.', 'success')
    return response


if __name__ == '__main__':
    app.run(debug=True)
