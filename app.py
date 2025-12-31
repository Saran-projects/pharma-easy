from flask import Flask, render_template, request, redirect, session
from flask_mysqldb import MySQL
import matplotlib
matplotlib.use('Agg')   # IMPORTANT for Flask
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from flask import jsonify

def plot_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    img = base64.b64encode(buf.getvalue()).decode()
    plt.close(fig)
    return img

app = Flask(__name__)
app.secret_key = "pharmacy_secret_key"

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'saran'
app.config['MYSQL_DB'] = 'pharmacy_db'

mysql = MySQL(app)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')

    cursor = mysql.connection.cursor()
    cursor.execute(
        "SELECT user_id, role FROM users WHERE username=%s AND password=%s AND role=%s",
        (username, password, role)
    )
    user = cursor.fetchone()

    if user:
        session['user_id'] = user[0]
        session['role'] = user[1]
        return jsonify(success=True, role=user[1])

    return jsonify(success=False, message="Invalid credentials"), 401

@app.route('/api/session')
def api_session():
    if 'user_id' in session:
        return jsonify(logged_in=True, role=session['role'])
    return jsonify(logged_in=False)

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify(success=True)

@app.route('/api/suppliers')
def get_suppliers():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT supplier_id, supplier_name FROM suppliers")
    rows = cursor.fetchall()

    return [
        {"id": r[0], "name": r[1]}
        for r in rows
    ]

@app.route('/api/medicines')
def get_medicines():
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT medicine_id, medicine_name, price, quantity
        FROM medicines
        WHERE quantity > 0
    """)
    rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "price": float(r[2]),
            "quantity": r[3]
        }
        for r in rows
    ]




@app.route('/')
def home():
    with open('templates/vue_app.html',encoding='utf-8') as f:
        return f.read()


@app.route('/admin_dashboard')
def admin_dashboard_vue():
    with open('templates/admin_dashboard.html', encoding='utf-8') as f:
        return f.read()



@app.route('/add_medicine', methods=['POST'])
def add_medicine():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 403

    data = request.get_json()

    name = data['name']
    batch = data['batch']
    expiry = data['expiry']
    quantity = data['quantity']
    price = data['price']
    supplier_id = data['supplier_id']

    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO medicines
        (medicine_name, batch_no, expiry_date, quantity, price, supplier_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, batch, expiry, quantity, price, supplier_id))

    mysql.connection.commit()
    return "OK", 200

@app.route('/add_medicine_vue')
def add_medicine_vue():
    with open('templates/add_medicine.html', encoding='utf-8') as f:
        return f.read()


@app.route('/api/medicines_admin')
def medicines_admin():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 403

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT m.medicine_name, m.quantity, m.price, s.supplier_name
        FROM medicines m
        JOIN suppliers s ON m.supplier_id = s.supplier_id
    """)
    rows = cursor.fetchall()

    return [
        {
            "name": r[0],
            "quantity": r[1],
            "price": float(r[2]),
            "supplier": r[3]
        }
        for r in rows
    ]
@app.route('/view_medicines_vue')
def view_medicines_vue():
    with open('templates/view_medicines.html', encoding='utf-8') as f:
        return f.read()


@app.route('/add_supplier', methods=['POST'])
def add_supplier():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 403

    data = request.get_json()   # ✅ JSON from Vue

    name = data['name']
    contact = data['contact']
    email = data['email']
    address = data['address']

    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO suppliers (supplier_name, contact_number, email, address)
        VALUES (%s, %s, %s, %s)
    """, (name, contact, email, address))

    mysql.connection.commit()

    return "OK", 200


@app.route('/add_supplier_vue')
def add_supplier_vue():
    with open('templates/add_supplier.html', encoding='utf-8') as f:
        return f.read()







@app.route('/api/staff')
def get_staff():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 403

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT user_id, username FROM users WHERE role='staff'")
    rows = cursor.fetchall()

    return [{"id": r[0], "username": r[1]} for r in rows]

@app.route('/api/delete_staff/<int:staff_id>', methods=['DELETE'])
def delete_staff(staff_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM users WHERE user_id=%s", (staff_id,))
    mysql.connection.commit()
    return "OK", 200

@app.route('/manage_staff_vue')
def manage_staff_vue():
    with open('templates/manage_staff.html', encoding='utf-8') as f:
        return f.read()



@app.route('/generate_bill', methods=['POST'])
def generate_bill():
    if 'role' not in session or session['role'] != 'staff':
        return "Unauthorized", 403

    data = request.get_json()
    medicine_id = data['medicine_id']
    qty = int(data['quantity'])

    cursor = mysql.connection.cursor()

    # Get medicine
    cursor.execute(
        "SELECT price, quantity FROM medicines WHERE medicine_id=%s",
        (medicine_id,)
    )
    med = cursor.fetchone()

    if not med:
        return "Medicine not found", 400

    price, stock = med

    if qty > stock:
        return "Insufficient stock", 400

    total = qty * price

    # Create bill
    cursor.execute(
        "INSERT INTO bills (staff_id, total_amount) VALUES (%s, %s)",
        (session['user_id'], total)
    )
    bill_id = cursor.lastrowid

    # Bill item
    cursor.execute("""
        INSERT INTO bill_items (bill_id, medicine_id, quantity, price)
        VALUES (%s, %s, %s, %s)
    """, (bill_id, medicine_id, qty, price))

    # Update stock
    cursor.execute("""
        UPDATE medicines
        SET quantity = quantity - %s
        WHERE medicine_id = %s
    """, (qty, medicine_id))

    mysql.connection.commit()

    return {"total": total}, 200

@app.route('/staff_billing')
def staff_billing_vue():
    with open('templates/staff_billing.html', encoding='utf-8') as f:
        return f.read()




@app.route('/api/billing_history')
def billing_history_api():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 403

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT b.bill_id, b.bill_date, b.total_amount, u.username
        FROM bills b
        JOIN users u ON b.staff_id = u.user_id
        ORDER BY b.bill_date DESC
    """)
    rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "date": str(r[1]),
            "total": float(r[2]),
            "staff": r[3]
        }
        for r in rows
    ]
@app.route('/billing_history_vue')
def billing_history_vue():
    with open('templates/billing_history.html', encoding='utf-8') as f:
        return f.read()


@app.route('/low_stock')
def low_stock():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/')

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT medicine_name, quantity FROM medicines WHERE quantity < 10")
    meds = cursor.fetchall()

    return str(meds)

@app.route('/expiry_alert')
def expiry_alert():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/')

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT medicine_name, expiry_date 
        FROM medicines 
        WHERE expiry_date <= CURDATE()
    """)
    meds = cursor.fetchall()

    return str(meds)

@app.route('/add_staff', methods=['POST'])
def add_staff():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 403

    data = request.get_json()

    username = data['username']
    password = data['password']

    cursor = mysql.connection.cursor()
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, 'staff')",
        (username, password)
    )
    mysql.connection.commit()

    return "OK", 200

@app.route('/add_staff_vue')
def add_staff_vue():
    with open('templates/add_staff.html', encoding='utf-8') as f:
        return f.read()


@app.route('/analytics/sales_histogram')
def sales_histogram():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT total_amount FROM bills")
    data = [float(r[0]) for r in cursor.fetchall()]

    fig = plt.figure()
    plt.hist(data, bins=10)
    plt.title("Sales Distribution")
    plt.xlabel("Amount")
    plt.ylabel("Frequency")

    return plot_to_base64(fig)

@app.route('/analytics/monthly_sales')
def monthly_sales():
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT MONTH(bill_date), SUM(total_amount)
        FROM bills
        GROUP BY MONTH(bill_date)
    """)
    rows = cursor.fetchall()

    months = [str(r[0]) for r in rows]
    totals = [float(r[1]) for r in rows]

    fig = plt.figure()
    plt.bar(months, totals)
    plt.title("Monthly Sales")
    plt.xlabel("Month")
    plt.ylabel("Total Sales")

    return plot_to_base64(fig)

@app.route('/analytics/supply_expense')
def supply_expense():
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT MONTH(b.bill_date), SUM(bi.price * bi.quantity)
        FROM bill_items bi
        JOIN bills b ON bi.bill_id = b.bill_id
        GROUP BY MONTH(b.bill_date)
    """)
    rows = cursor.fetchall()

    months = [str(r[0]) for r in rows]
    expense = [float(r[1]) for r in rows]

    fig = plt.figure()
    plt.bar(months, expense)
    plt.title("Monthly Supply Expense")
    plt.xlabel("Month")
    plt.ylabel("Expense")

    return plot_to_base64(fig)

@app.route('/analytics_vue')
def analytics_vue():
    with open('templates/analytics.html', encoding='utf-8') as f:
        return f.read()


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)
