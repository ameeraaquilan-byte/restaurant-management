from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import sqlite3
import hashlib
import os
import json
from datetime import datetime
import base64
import uuid
import itertools
from collections import defaultdict

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = 'chelicious_secret_key_2024'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

DB_PATH = 'chelicious.db'
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─────────────────────────────────────────────
# APRIORI / ASSOCIATION RULES  (Machine Learning — Frequent Pattern Mining)
# ─────────────────────────────────────────────
RULES = {}

def mine_rules(min_support=0.05, min_confidence=0.3):
    global RULES
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT items FROM orders WHERE payment_status='Paid'")
        rows = c.fetchall()
        conn.close()

        if len(rows) < 5:
            RULES = {}
            return

        transactions = []
        for row in rows:
            items = json.loads(row['items'])
            names = frozenset(i['name'] for i in items if i.get('name'))
            if len(names) >= 2:
                transactions.append(names)

        n = len(transactions)
        if n == 0:
            RULES = {}
            return

        item_count = defaultdict(int)
        pair_count = defaultdict(int)

        for t in transactions:
            for item in t:
                item_count[item] += 1
            for pair in itertools.combinations(sorted(t), 2):
                pair_count[pair] += 1

        freq_items = {k for k, v in item_count.items() if v / n >= min_support}
        freq_pairs = {k: v for k, v in pair_count.items()
                      if v / n >= min_support and k[0] in freq_items and k[1] in freq_items}

        rules = defaultdict(list)
        for (a, b), count in freq_pairs.items():
            conf_ab = count / item_count[a] if item_count[a] else 0
            conf_ba = count / item_count[b] if item_count[b] else 0
            if conf_ab >= min_confidence:
                rules[frozenset([a])].append((b, round(conf_ab, 2)))
            if conf_ba >= min_confidence:
                rules[frozenset([b])].append((a, round(conf_ba, 2)))

        RULES = {k: [name for name, _ in sorted(v, key=lambda x: -x[1])[:3]]
                 for k, v in rules.items()}

    except Exception as e:
        print(f"[mine_rules] Warning: {e}")
        RULES = {}

# ─────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def format_timestamp(ts_str):
    try:
        dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%b %d, %Y %I:%M %p')
    except:
        return ts_str

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'customer'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
        image_url TEXT,
        available INTEGER NOT NULL DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        items TEXT NOT NULL,
        total_price REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending',
        payment_method TEXT NOT NULL,
        payment_status TEXT NOT NULL DEFAULT 'Unpaid',
        order_type TEXT NOT NULL DEFAULT 'Dine-in',
        timestamp TEXT NOT NULL,
        notified INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    for migration in [
        "ALTER TABLE menu ADD COLUMN available INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE orders ADD COLUMN notified INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN order_type TEXT NOT NULL DEFAULT 'Dine-in'",
    ]:
        try:
            c.execute(migration)
            conn.commit()
        except:
            pass

    # Seed admin
    c.execute("SELECT * FROM users WHERE email='admin@chelicious.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                  ('Admin', 'admin@chelicious.com', hash_password('admin123'), 'admin'))

    # Seed cashier
    c.execute("SELECT * FROM users WHERE email='cashier@chelicious.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                  ('Cashier1', 'cashier@chelicious.com', hash_password('cash123'), 'cashier'))

    # Seed kitchen
    c.execute("SELECT * FROM users WHERE email='kitchen@chelicious.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                  ('Kitchen1', 'kitchen@chelicious.com', hash_password('kitch123'), 'kitchen'))

    # Seed waiter
    c.execute("SELECT * FROM users WHERE email='waiter@chelicious.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                  ('Waiter1', 'waiter@chelicious.com', hash_password('wait123'), 'waiter'))

    # Seed menu
    c.execute("SELECT COUNT(*) FROM menu")
    if c.fetchone()[0] == 0:
        menu_items = [
            ('Grilled Chicken', 'Food', 185.00, 'Juicy grilled chicken with herbs', '🍗', 1),
            ('Beef Burger', 'Food', 210.00, 'Classic beef patty with veggies', '🍔', 1),
            ('Spaghetti Bolognese', 'Food', 175.00, 'Rich meat sauce pasta', '🍝', 1),
            ('Crispy Pork Sisig', 'Food', 165.00, 'Filipino sizzling sisig', '🥩', 1),
            ('Chicken Adobo', 'Food', 155.00, 'Classic Filipino adobo', '🍖', 1),
            ('Pancit Canton', 'Food', 140.00, 'Stir-fried noodles', '🍜', 1),
            ('Fish & Chips', 'Food', 195.00, 'Crispy battered fish with fries', '🐟', 1),
            ('Caesar Salad', 'Food', 130.00, 'Fresh romaine with caesar dressing', '🥗', 1),
            ('Iced Coffee', 'Drinks', 85.00, 'Cold brew with milk', '☕', 1),
            ('Mango Shake', 'Drinks', 95.00, 'Fresh mango blended drink', '🥭', 1),
            ('Lemonade', 'Drinks', 75.00, 'Fresh squeezed lemon drink', '🍋', 1),
            ('Iced Tea', 'Drinks', 65.00, 'Classic sweet iced tea', '🧋', 1),
            ('Hot Chocolate', 'Drinks', 80.00, 'Rich creamy hot choco', '🍫', 1),
            ('Buko Juice', 'Drinks', 70.00, 'Fresh coconut juice', '🥥', 1),
            ('French Fries', 'Snacks', 75.00, 'Crispy golden fries', '🍟', 1),
            ('Onion Rings', 'Snacks', 80.00, 'Beer-battered onion rings', '🧅', 1),
            ('Spring Rolls', 'Snacks', 85.00, 'Crispy veggie spring rolls', '🥚', 1),
            ('Nachos', 'Snacks', 110.00, 'Loaded nachos with cheese', '🌮', 1),
            ('Chocolate Cake', 'Desserts', 120.00, 'Rich moist chocolate cake', '🎂', 1),
            ('Leche Flan', 'Desserts', 95.00, 'Classic Filipino custard', '🍮', 1),
            ('Halo-Halo', 'Desserts', 110.00, 'Mixed Filipino shaved ice dessert', '🍨', 1),
            ('Turon', 'Desserts', 60.00, 'Fried banana rolls with langka', '🍌', 1),
            ('Margherita Pizza', 'Pizza', 245.00, 'Classic tomato, mozzarella, fresh basil', '🍕', 1),
            ('Pepperoni Pizza', 'Pizza', 265.00, 'Loaded pepperoni with mozzarella', '🍕', 1),
            ('BBQ Chicken Pizza', 'Pizza', 275.00, 'Smoky BBQ sauce with grilled chicken', '🍕', 1),
            ('Hawaiian Pizza', 'Pizza', 255.00, 'Ham, pineapple, and mozzarella', '🍕', 1),
            ('Four Cheese Pizza', 'Pizza', 285.00, 'Mozzarella, cheddar, parmesan, gouda', '🍕', 1),
        ]
        c.executemany("INSERT INTO menu (name, category, price, description, image_url, available) VALUES (?,?,?,?,?,?)", menu_items)

    conn.commit()
    conn.close()
    mine_rules()

# ─────────────────────────────────────────────
# SERVE FRONTEND
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ─────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not name or not email or not password:
            return jsonify({'error': 'All fields are required.'}), 400
        if len(password) < 6 or len(password) > 10:
            return jsonify({'error': 'Password must be 6–10 characters only.'}), 400

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'Email already registered.'}), 400

        c.execute("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)",
                  (name, email, hash_password(password), 'customer'))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Registration successful! You can now login.'}), 201
    except Exception as e:
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()

        if not email or not password:
            return jsonify({'error': 'Email and password are required.'}), 400

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=? AND password=?",
                  (email, hash_password(password)))
        user = c.fetchone()
        conn.close()

        if not user:
            return jsonify({'error': 'Invalid email or password.'}), 401

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        session.modified = True

        return jsonify({
            'message': 'Login successful!',
            'user': {'id': user['id'], 'name': user['name'], 'role': user['role']}
        }), 200
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully.'}), 200

@app.route('/api/me', methods=['GET'])
def me():
    if 'user_id' not in session:
        return jsonify({'user': None}), 200
    return jsonify({'user': {
        'id': session['user_id'],
        'name': session['user_name'],
        'role': session['user_role']
    }}), 200

# ─────────────────────────────────────────────
# MENU ROUTES
# ─────────────────────────────────────────────

@app.route('/api/menu', methods=['GET'])
def get_menu():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM menu WHERE available=1 ORDER BY category, name")
        items = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({'menu': items}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to load menu: {str(e)}'}), 500

@app.route('/api/menu/all', methods=['GET'])
def get_menu_all():
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM menu ORDER BY category, name")
        items = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({'menu': items}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to load menu: {str(e)}'}), 500

# ─────────────────────────────────────────────
# BEST SELLERS ENDPOINT  (Popularity-Based Recommendation)
# ─────────────────────────────────────────────
# HOW IT WORKS:
#   1. Scan all paid orders and count total qty ordered per item name.
#   2. Only items with total_qty >= 10 qualify as "Best Sellers".
#   3. Sort by qty descending, return top 8 with full menu details (image, price, etc).
#   4. Frontend shows these as a "Best Sellers" banner at the top of the homepage.

@app.route('/api/menu/bestsellers', methods=['GET'])
def get_bestsellers():
    try:
        conn = get_db()
        c = conn.cursor()

        # Get all paid orders
        c.execute("SELECT items FROM orders WHERE payment_status='Paid'")
        rows = c.fetchall()

        # Count qty per item name
        item_qty = defaultdict(int)
        for row in rows:
            items = json.loads(row['items'])
            for item in items:
                name = item.get('name', '')
                qty = item.get('qty', 1)
                if name:
                    item_qty[name] += qty

        # Filter: only items with >= 10 total orders
        MIN_ORDERS = 10
        qualified = {name: qty for name, qty in item_qty.items() if qty >= MIN_ORDERS}

        if not qualified:
            conn.close()
            return jsonify({'bestsellers': [], 'min_orders': MIN_ORDERS}), 200

        # Sort by qty desc, top 8
        top_names = sorted(qualified.keys(), key=lambda n: qualified[n], reverse=True)[:8]

        # Fetch full menu details for each
        bestsellers = []
        for name in top_names:
            c.execute("SELECT * FROM menu WHERE name=? AND available=1", (name,))
            row = c.fetchone()
            if row:
                item = dict(row)
                item['total_orders'] = qualified[name]
                bestsellers.append(item)

        conn.close()
        return jsonify({'bestsellers': bestsellers, 'min_orders': MIN_ORDERS}), 200

    except Exception as e:
        return jsonify({'error': f'Failed to load bestsellers: {str(e)}', 'bestsellers': []}), 200


@app.route('/api/menu', methods=['POST'])
def add_menu_item():
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        category = data.get('category', '').strip()
        price = data.get('price')
        description = data.get('description', '').strip()
        image_url = data.get('image_url', '').strip()

        if not name or not category or not price:
            return jsonify({'error': 'Name, category, and price are required.'}), 400

        image_path = image_url
        if image_url and image_url.startswith('data:image'):
            image_path = save_base64_image(image_url)

        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO menu (name, category, price, description, image_url, available) VALUES (?,?,?,?,?,1)",
                  (name, category, float(price), description, image_path))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Menu item added.'}), 201
    except Exception as e:
        return jsonify({'error': f'Failed to add menu item: {str(e)}'}), 500

@app.route('/api/menu/<int:item_id>', methods=['PUT'])
def update_menu_item(item_id):
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        data = request.get_json()

        if data.get('restore'):
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE menu SET available=1 WHERE id=?", (item_id,))
            conn.commit()
            conn.close()
            return jsonify({'message': 'Menu item restored.'}), 200

        name = data.get('name', '').strip()
        category = data.get('category', '').strip()
        price = data.get('price')
        description = data.get('description', '').strip()
        image_url = data.get('image_url', '').strip()

        image_path = image_url
        if image_url and image_url.startswith('data:image'):
            image_path = save_base64_image(image_url)

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE menu SET name=?, category=?, price=?, description=?, image_url=?, available=1 WHERE id=?",
                  (name, category, float(price), description, image_path, item_id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Menu item updated.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to update menu item: {str(e)}'}), 500

@app.route('/api/menu/<int:item_id>', methods=['DELETE'])
def delete_menu_item(item_id):
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE menu SET available=0 WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Menu item hidden.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to hide item: {str(e)}'}), 500

def save_base64_image(data_url):
    try:
        header, encoded = data_url.split(',', 1)
        ext = 'jpg'
        if 'png' in header: ext = 'png'
        elif 'gif' in header: ext = 'gif'
        elif 'webp' in header: ext = 'webp'
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(encoded))
        return f'/uploads/{filename}'
    except Exception as e:
        return ''

# ─────────────────────────────────────────────
# RECOMMENDATION ROUTE  (Apriori / Association Rules)
# ─────────────────────────────────────────────

@app.route('/api/menu/recommendations', methods=['POST'])
def get_recommendations():
    try:
        data = request.get_json()
        cart_names = set([name.strip() for name in data.get('item_names', [])])

        suggestions = set()

        for name in cart_names:
            key = frozenset([name])
            for suggested in RULES.get(key, []):
                if suggested and suggested not in cart_names:
                    suggestions.add(suggested)

        if len(cart_names) >= 2:
            for pair in itertools.combinations(sorted(cart_names), 2):
                key = frozenset(pair)
                for suggested in RULES.get(key, []):
                    if suggested and suggested not in cart_names:
                        suggestions.add(suggested)

        conn = get_db()
        cur = conn.cursor()
        recs = []

        if not suggestions:
            placeholders = ','.join('?' * len(cart_names)) if cart_names else "''"
            query = f"SELECT * FROM menu WHERE available=1"
            if cart_names:
                query += f" AND name NOT IN ({placeholders})"
            query += " LIMIT 4"
            cur.execute(query, list(cart_names))
            recs = [dict(row) for row in cur.fetchall()]
        else:
            for name in list(suggestions)[:4]:
                cur.execute("SELECT * FROM menu WHERE name=? AND available=1", (name,))
                row = cur.fetchone()
                if row:
                    recs.append(dict(row))

        conn.close()
        return jsonify({'recommendations': recs}), 200

    except Exception as e:
        return jsonify({'recommendations': [], 'error': str(e)}), 200

# ─────────────────────────────────────────────
# ORDER ROUTES
# ─────────────────────────────────────────────

@app.route('/api/orders', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return jsonify({'error': 'Login required to place orders.'}), 401
    try:
        data = request.get_json()
        items = data.get('items')
        total_price = data.get('total_price')
        payment_method = data.get('payment_method', '').strip()
        order_type = data.get('order_type', 'Dine-in').strip()

        if not items or not total_price or not payment_method:
            return jsonify({'error': 'Order details are incomplete.'}), 400

        payment_status = 'Unpaid'
        if payment_method in ('GCash', 'Card Payment'):
            payment_status = 'Paid'

        conn = get_db()
        c = conn.cursor()
        c.execute("""INSERT INTO orders
                     (user_id, items, total_price, status, payment_method, payment_status, order_type, timestamp, notified)
                     VALUES (?,?,?,?,?,?,?,?,0)""",
                  (session['user_id'], json.dumps(items), float(total_price),
                   'Pending', payment_method, payment_status, order_type,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        order_id = c.lastrowid
        conn.commit()
        conn.close()

        if payment_status == 'Paid':
            mine_rules()

        return jsonify({'message': 'Order placed successfully!', 'order_id': order_id}), 201
    except Exception as e:
        return jsonify({'error': f'Failed to place order: {str(e)}'}), 500

@app.route('/api/orders/<int:order_id>/cancel', methods=['PUT'])
def cancel_order(order_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Login required.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        order = c.fetchone()
        if not order:
            conn.close()
            return jsonify({'error': 'Order not found.'}), 404

        role = session.get('user_role')
        user_id = session.get('user_id')

        if role == 'customer':
            if order['user_id'] != user_id:
                conn.close()
                return jsonify({'error': 'Not your order.'}), 403
            if order['status'] != 'Pending':
                conn.close()
                return jsonify({'error': 'Only Pending orders can be cancelled.'}), 400
        elif role not in ('admin', 'cashier'):
            conn.close()
            return jsonify({'error': 'Unauthorized.'}), 401

        c.execute("UPDATE orders SET status='Cancelled' WHERE id=?", (order_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Order cancelled.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to cancel order: {str(e)}'}), 500

@app.route('/api/orders/my', methods=['GET'])
def my_orders():
    if 'user_id' not in session:
        return jsonify({'error': 'Login required.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session['user_id'],))
        orders = []
        for row in c.fetchall():
            o = dict(row)
            o['items'] = json.loads(o['items'])
            o['timestamp'] = format_timestamp(o['timestamp'])
            orders.append(o)
        conn.close()
        return jsonify({'orders': orders}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch orders: {str(e)}'}), 500

@app.route('/api/orders/notifications', methods=['GET'])
def get_notifications():
    if 'user_id' not in session:
        return jsonify({'notifications': []}), 200
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT id, items, total_price, timestamp FROM orders
                     WHERE user_id=? AND status='Ready for Pickup' AND notified=0""",
                  (session['user_id'],))
        notifs = []
        ids = []
        for row in c.fetchall():
            o = dict(row)
            o['items'] = json.loads(o['items'])
            o['timestamp'] = format_timestamp(o['timestamp'])
            notifs.append(o)
            ids.append(o['id'])
        if ids:
            placeholders = ','.join('?' * len(ids))
            c.execute(f"UPDATE orders SET notified=1 WHERE id IN ({placeholders})", ids)
            conn.commit()
        conn.close()
        return jsonify({'notifications': notifs}), 200
    except Exception as e:
        return jsonify({'notifications': []}), 200

@app.route('/api/orders/all', methods=['GET'])
def all_orders():
    if session.get('user_role') not in ('admin', 'cashier', 'kitchen', 'waiter'):
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT o.*, u.name as customer_name, u.email as customer_email
                     FROM orders o JOIN users u ON o.user_id = u.id
                     ORDER BY o.id DESC""")
        orders = []
        for row in c.fetchall():
            o = dict(row)
            o['items'] = json.loads(o['items'])
            o['timestamp'] = format_timestamp(o['timestamp'])
            orders.append(o)
        conn.close()
        return jsonify({'orders': orders}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch orders: {str(e)}'}), 500

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    if session.get('user_role') not in ('admin', 'kitchen', 'waiter'):
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        data = request.get_json()
        new_status = data.get('status', '').strip()
        valid = ['Pending', 'Preparing', 'Ready for Pickup', 'Completed', 'Cancelled']
        if new_status not in valid:
            return jsonify({'error': 'Invalid status.'}), 400

        role = session.get('user_role')
        if role == 'waiter' and new_status != 'Completed':
            return jsonify({'error': 'Waiters can only mark orders as Completed.'}), 403

        conn = get_db()
        c = conn.cursor()
        if new_status == 'Ready for Pickup':
            c.execute("UPDATE orders SET status=?, notified=0 WHERE id=?", (new_status, order_id))
        else:
            c.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
        conn.commit()
        conn.close()
        return jsonify({'message': f'Order status updated to {new_status}.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to update order status: {str(e)}'}), 500

@app.route('/api/orders/<int:order_id>/payment', methods=['PUT'])
def update_payment_status(order_id):
    if session.get('user_role') not in ('admin', 'cashier'):
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        data = request.get_json()
        payment_status = data.get('payment_status', '').strip()
        if payment_status not in ('Paid', 'Unpaid'):
            return jsonify({'error': 'Invalid payment status.'}), 400

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE orders SET payment_status=? WHERE id=?", (payment_status, order_id))
        conn.commit()
        conn.close()

        if payment_status == 'Paid':
            mine_rules()

        return jsonify({'message': 'Payment status updated.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to update payment: {str(e)}'}), 500

# ─────────────────────────────────────────────
# RECEIPT
# ─────────────────────────────────────────────

@app.route('/api/orders/<int:order_id>/receipt', methods=['GET'])
def get_receipt(order_id):
    if session.get('user_role') not in ('admin', 'cashier'):
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT o.*, u.name as customer_name, u.email as customer_email
                     FROM orders o JOIN users u ON o.user_id = u.id
                     WHERE o.id=?""", (order_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return jsonify({'error': 'Order not found.'}), 404
        o = dict(row)
        o['items'] = json.loads(o['items'])
        o['timestamp'] = format_timestamp(o['timestamp'])
        return jsonify({'receipt': o}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch receipt: {str(e)}'}), 500

# ─────────────────────────────────────────────
# ADMIN: USER MANAGEMENT
# ─────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
def get_users():
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, name, email, role FROM users ORDER BY role, name")
        users = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({'users': users}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch users: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    if user_id == session.get('user_id'):
        return jsonify({'error': 'Cannot delete your own account.'}), 400
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'User deleted.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to delete user: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/role', methods=['PUT'])
def update_user_role(user_id):
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        data = request.get_json()
        new_role = data.get('role', '').strip()
        if new_role not in ('customer', 'cashier', 'kitchen', 'waiter', 'admin'):
            return jsonify({'error': 'Invalid role.'}), 400

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'User role updated.'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to update user role: {str(e)}'}), 500

# ─────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────

@app.route('/api/reports/sales', methods=['GET'])
def sales_report():
    if session.get('user_role') not in ('admin', 'cashier'):
        return jsonify({'error': 'Unauthorized.'}), 401
    try:
        conn = get_db()
        c = conn.cursor()

        date_param = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

        c.execute("""SELECT COUNT(*) as total_orders,
                            COALESCE(SUM(total_price), 0) as total_sales
                     FROM orders
                     WHERE payment_status='Paid'
                       AND substr(timestamp,1,10)=?""", (date_param,))
        summary = dict(c.fetchone())

        c.execute("""SELECT payment_method,
                            COUNT(*) as count,
                            COALESCE(SUM(total_price),0) as total
                     FROM orders
                     WHERE payment_status='Paid'
                       AND substr(timestamp,1,10)=?
                     GROUP BY payment_method""", (date_param,))
        by_method = [dict(r) for r in c.fetchall()]

        c.execute("""SELECT items FROM orders
                     WHERE payment_status='Paid'
                       AND substr(timestamp,1,10)=?""", (date_param,))
        item_counts = {}
        item_revenue = {}
        for row in c.fetchall():
            items = json.loads(row['items'])
            for it in items:
                name = it.get('name', '')
                qty = it.get('qty', 1)
                price = it.get('price', 0)
                item_counts[name] = item_counts.get(name, 0) + qty
                item_revenue[name] = item_revenue.get(name, 0) + (qty * price)

        top_items = sorted([
            {'name': k, 'qty': item_counts[k], 'revenue': round(item_revenue[k], 2)}
            for k in item_counts
        ], key=lambda x: x['qty'], reverse=True)

        conn.close()
        return jsonify({
            'date': date_param,
            'summary': summary,
            'by_payment_method': by_method,
            'top_items': top_items
        }), 200
    except Exception as e:
        return jsonify({'error': f'Report error: {str(e)}'}), 500

# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    init_db()
    app.run(debug=True, port=5000)