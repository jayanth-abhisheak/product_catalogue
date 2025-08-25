from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

# ----------------------------
# App Setup
# ----------------------------
app = Flask(__name__)
app.secret_key = "secretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///catalogue.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = "static/uploads"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ----------------------------
# Models
# ----------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20), default="user")  # user or admin

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(200))
    price = db.Column(db.Float)
    stock = db.Column(db.Integer)
    image = db.Column(db.String(200))  # relative path (uploads/filename.jpg)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    quantity = db.Column(db.Integer, default=1)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    quantity = db.Column(db.Integer)
    address = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Pending")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------------
# Routes
# ----------------------------
@app.route('/')
def home():
    return redirect(url_for('catalogue'))

# --- Signup ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "danger")
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed_pw, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash("Account created! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')

# --- Login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('catalogue'))
        else:
            flash("Invalid credentials", "danger")
    return render_template('login.html')

# --- Logout ---
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Catalogue ---
@app.route('/catalogue')
def catalogue():
    query = request.args.get("q")
    min_price = request.args.get("min")
    max_price = request.args.get("max")

    products = Product.query
    if query:
        products = products.filter(Product.name.contains(query) | Product.description.contains(query))
    if min_price:
        products = products.filter(Product.price >= float(min_price))
    if max_price:
        products = products.filter(Product.price <= float(max_price))

    return render_template("catalogue.html", products=products.all())

# ----------------------------
# Cart System
# ----------------------------
@app.route('/add_to_cart/<int:product_id>')
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    cart_item = Cart.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = Cart(user_id=current_user.id, product_id=product.id, quantity=1)
        db.session.add(cart_item)
    db.session.commit()
    flash("Added to cart!", "success")
    return redirect(url_for('catalogue'))

@app.route('/cart')
@login_required
def cart():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    products = []
    total = 0
    for item in cart_items:
        product = Product.query.get(item.product_id)
        products.append({"item": item, "product": product})
        total += product.price * item.quantity
    return render_template("cart.html", products=products, total=total)

@app.route('/remove_from_cart/<int:item_id>')
@login_required
def remove_from_cart(item_id):
    item = Cart.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for('cart'))
    db.session.delete(item)
    db.session.commit()
    flash("Item removed from cart.", "success")
    return redirect(url_for('cart'))

# ----------------------------
# Orders
# ----------------------------
@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    address = request.form['address']
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash("Cart is empty!", "danger")
        return redirect(url_for('cart'))

    for item in cart_items:
        order = Order(user_id=current_user.id, product_id=item.product_id, quantity=item.quantity, address=address)
        db.session.add(order)
        db.session.delete(item)  # empty cart after order
    db.session.commit()
    flash("Order placed successfully!", "success")
    return redirect(url_for('my_orders'))

@app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template("my_orders.html", orders=orders)

@app.route('/admin/orders')
@login_required
def admin_orders():
    if current_user.role != "admin":
        flash("Unauthorized access", "danger")
        return redirect(url_for('catalogue'))
    orders = Order.query.all()
    return render_template("admin_orders.html", orders=orders)

# ----------------------------
# Admin - Manage Products
# ----------------------------
@app.route('/admin/products')
@login_required
def admin_products():
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('catalogue'))
    products = Product.query.all()
    return render_template('admin_products.html', products=products)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('catalogue'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])

        # ✅ Image upload fix
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != "":
                filename = file.filename
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(upload_path)
                image_filename = f"uploads/{filename}"  # relative path

        new_product = Product(name=name, description=description, price=price, stock=stock, image=image_filename)
        db.session.add(new_product)
        db.session.commit()
        flash("Product added successfully!", "success")
        return redirect(url_for('admin_products'))

    return render_template('add_product.html')

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('catalogue'))

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.stock = int(request.form['stock'])

        # ✅ Image upload fix
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != "":
                filename = file.filename
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(upload_path)
                product.image = f"uploads/{filename}"  # relative path

        db.session.commit()
        flash("Product updated successfully!", "success")
        return redirect(url_for('admin_products'))

    return render_template('edit_product.html', product=product)

@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('catalogue'))

    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully!", "success")
    return redirect(url_for('admin_products'))

# ----------------------------
# Initialize DB
# ----------------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
