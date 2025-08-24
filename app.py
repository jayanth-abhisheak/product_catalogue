from flask import (
    Flask, render_template, session, redirect, url_for, request, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, login_required, logout_user,
    current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"   # change in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ----------------------------
# Models
# ----------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")  # "user" or "admin"

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(200), default="placeholder.jpg")

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="Pending")  # Pending/Shipped/Delivered
    address = db.Column(db.Text, nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="orders")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price_at_purchase = db.Column(db.Integer, nullable=False)

    order = db.relationship("Order", backref="items")
    product = db.relationship("Product")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------------
# Helpers
# ----------------------------
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if current_user.role != "admin":
            flash("Admin access required.", "warning")
            return redirect(url_for("home"))
        return func(*args, **kwargs)
    return wrapper

def seed_data():
    """Create tables, an admin user (first user), and sample products if empty."""
    db.create_all()
    # Auto-create one admin if no users exist (email: admin@demo.com / password: admin123)
    if User.query.count() == 0:
        admin = User(name="Admin", email="admin@demo.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
    # Sample products
    if Product.query.count() == 0:
        samples = [
            Product(name="Laptop", description="Powerful laptop for work and gaming",
                    price=55000, stock=10, image="laptop.jpg"),
            Product(name="Headphones", description="Noise-cancelling wireless headphones",
                    price=2000, stock=50, image="headphones.jpg"),
            Product(name="Smartphone", description="Latest Android smartphone",
                    price=30000, stock=25, image="smartphone.jpg"),
        ]
        db.session.add_all(samples)
        db.session.commit()

# ----------------------------
# Init DB and seed data (Flask 3.x fix)
# ----------------------------
with app.app_context():
    os.makedirs("static", exist_ok=True)
    seed_data()

# ----------------------------
# Public routes (Catalogue/Search/Details/Cart)
# ----------------------------
@app.route("/")
def home():
    products = Product.query.all()
    return render_template("catalogue.html", products=products)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("product_detail.html", product=product)

@app.route("/search")
def search():
    query = request.args.get("query", "").strip().lower()
    price_range = request.args.get("price_range", "")
    q = Product.query
    if query:
        q = q.filter(
            db.or_(
                db.func.lower(Product.name).contains(query),
                db.func.lower(Product.description).contains(query)
            )
        )
    products = q.all()
    if price_range == "low":
        products = [p for p in products if p.price < 5000]
    elif price_range == "medium":
        products = [p for p in products if 5000 <= p.price <= 30000]
    elif price_range == "high":
        products = [p for p in products if p.price > 30000]
    return render_template("catalogue.html", products=products)

# --- Cart in session: [{'id': product_id, 'qty': n}, ...] ---
def _get_cart():
    return session.get("cart", [])

def _save_cart(cart):
    session["cart"] = cart

@app.route("/add_to_cart/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    if product.stock <= 0:
        flash("Out of stock!", "warning")
        return redirect(url_for("home"))
    cart = _get_cart()
    # if already in cart, increase qty
    for item in cart:
        if item["id"] == product_id:
            item["qty"] += 1
            _save_cart(cart)
            return redirect(url_for("view_cart"))
    cart.append({"id": product_id, "qty": 1})
    _save_cart(cart)
    return redirect(url_for("view_cart"))

@app.route("/cart")
def view_cart():
    cart = _get_cart()
    items = []
    total = 0
    for entry in cart:
        p = Product.query.get(entry["id"])
        if not p:
            continue
        line_total = p.price * entry["qty"]
        total += line_total
        items.append({"product": p, "qty": entry["qty"], "line_total": line_total})
    return render_template("cart.html", items=items, total=total)

@app.route("/remove_from_cart/<int:index>", methods=["POST"])
def remove_from_cart(index):
    cart = _get_cart()
    if 0 <= index < len(cart):
        cart.pop(index)
        _save_cart(cart)
    return redirect(url_for("view_cart"))

# ----------------------------
# Auth (Sign Up / Login / Logout)
# ----------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "danger")
            return redirect(url_for("signup"))
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Signup successful. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("home"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("cart", None)
    return redirect(url_for("home"))

# ----------------------------
# Checkout & Orders
# ----------------------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart = _get_cart()
    if not cart:
        return redirect(url_for("view_cart"))

    if request.method == "POST":
        address = request.form["address"].strip()
        phone = request.form["phone"].strip()

        # Create order
        order = Order(user_id=current_user.id, address=address, phone=phone, status="Pending")
        db.session.add(order)
        db.session.flush()  # get order.id

        # Convert cart to order items, update stock
        for entry in cart:
            p = Product.query.get(entry["id"])
            if not p:
                continue
            qty = entry["qty"]
            if p.stock < qty:
                db.session.rollback()
                flash(f"Insufficient stock for {p.name}.", "danger")
                return redirect(url_for("view_cart"))
            p.stock -= qty
            item = OrderItem(order_id=order.id, product_id=p.id, quantity=qty, price_at_purchase=p.price)
            db.session.add(item)

        db.session.commit()
        session["cart"] = []
        return render_template("order_success.html", name=current_user.name)

    # GET
    items = []
    total = 0
    for entry in cart:
        p = Product.query.get(entry["id"])
        if not p:
            continue
        line_total = p.price * entry["qty"]
        total += line_total
        items.append({"product": p, "qty": entry["qty"], "line_total": line_total})
    return render_template("checkout.html", items=items, total=total)

@app.route("/my_orders")
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("my_orders.html", orders=orders)

# ----------------------------
# Admin: Product CRUD + View/Update Orders
# ----------------------------
@app.route("/admin/products")
@admin_required
def admin_products():
    products = Product.query.order_by(Product.id.desc()).all()
    return render_template("admin_products.html", products=products)

@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def admin_add_product():
    if request.method == "POST":
        name = request.form["name"].strip()
        description = request.form["description"].strip()
        price = int(request.form["price"])
        stock = int(request.form["stock"])
        image = request.form.get("image", "placeholder.jpg").strip() or "placeholder.jpg"
        p = Product(name=name, description=description, price=price, stock=stock, image=image)
        db.session.add(p)
        db.session.commit()
        return redirect(url_for("admin_products"))
    return render_template("product_form.html", product=None)

@app.route("/admin/products/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_product(pid):
    p = Product.query.get_or_404(pid)
    if request.method == "POST":
        p.name = request.form["name"].strip()
        p.description = request.form["description"].strip()
        p.price = int(request.form["price"])
        p.stock = int(request.form["stock"])
        p.image = request.form.get("image", "placeholder.jpg").strip() or "placeholder.jpg"
        db.session.commit()
        return redirect(url_for("admin_products"))
    return render_template("product_form.html", product=p)

@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_delete_product(pid):
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for("admin_products"))

@app.route("/admin/orders", methods=["GET", "POST"])
@admin_required
def admin_orders():
    if request.method == "POST":
        oid = int(request.form["order_id"])
        status = request.form["status"]
        order = Order.query.get_or_404(oid)
        order.status = status
        db.session.commit()
        return redirect(url_for("admin_orders"))
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin_orders.html", orders=orders)

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
