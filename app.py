import os
import pickle
import sqlite3
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- Paths ---------------- #
BASE_DIR = os.getcwd()
MODEL_PATH = os.path.join(BASE_DIR, "model.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")
DB_PATH = os.path.join(BASE_DIR, "users.db")

# ---------------- Database Setup ---------------- #
with sqlite3.connect(DB_PATH) as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            prediction TEXT NOT NULL,
            probability REAL NOT NULL,
            risk_level TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

# ---------------- Load Model & Scaler ---------------- #
with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)
with open(SCALER_PATH, "rb") as f:
    scaler = pickle.load(f)

# ---------------- Input Columns ---------------- #
columns = [
    'age', 'sex', 'blood_oxygen', 'heart_rate',
    'stress_level', 'weight', 'height',
    'smoking', 'drinking'
]

# ---------------- Login Required Decorator ---------------- #
from functools import wraps
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Please login to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------- Routes ---------------- #
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        with sqlite3.connect(DB_PATH) as conn:
            try:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
                flash("Signup successful! Please login.", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Username already exists!", "danger")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT password FROM users WHERE username=?", (username,))
            user = cur.fetchone()
        if user and check_password_hash(user[0], password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        flash("Invalid credentials!", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('last_prediction', None)
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))

# ---------------- Dashboard ---------------- #
@app.route('/dashboard')
@login_required
def dashboard():
    history_list = []
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT prediction, probability, risk_level, timestamp FROM predictions WHERE username=? ORDER BY timestamp DESC", (session['user'],))
        data = cur.fetchall()
        for row in data:
            history_list.append({
                "prediction": row[0],
                "probability": row[1],
                "risk_level": row[2],
                "timestamp": row[3]
            })
    return render_template('dashboard.html', username=session['user'], history=history_list)

# ---------------- Predict ---------------- #
@app.route('/predict', methods=['GET', 'POST'])
@login_required
def predict():
    prediction = None
    probability = None

    if request.method == 'POST':
        try:
            data = [float(request.form[col]) for col in columns]
            height_m = data[6] / 100
            bmi = data[5] / (height_m ** 2)
            data.append(bmi)
            df_input = pd.DataFrame([data], columns=columns + ['bmi'])
            scaled_input = scaler.transform(df_input)
            prob = np.max(model.predict_proba(scaled_input)) * 100
            probability = round(prob, 2)

            if prob < 33:
                prediction = "Low Risk"
                risk_level = "low_risk"
            elif prob < 66:
                prediction = "Medium Risk"
                risk_level = "medium_risk"
            else:
                prediction = "High Risk"
                risk_level = "high_risk"

            session['last_prediction'] = risk_level

            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO predictions (username, prediction, probability, risk_level)
                    VALUES (?, ?, ?, ?)
                """, (session['user'], prediction, probability, risk_level))
                conn.commit()

            # Redirect to result page
            return redirect(url_for('result'))

        except Exception as e:
            flash(f"Error in prediction: {e}", "danger")
            return redirect(url_for('predict'))

    return render_template('predict.html')

# ---------------- Result ---------------- #
@app.route('/result')
@login_required
def result():
    risk_level = session.get('last_prediction', 'low_risk')

    # Determine prediction text & probability from DB
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT prediction, probability FROM predictions WHERE username=? ORDER BY timestamp DESC LIMIT 1", (session['user'],))
        last_pred = cur.fetchone()
        prediction = last_pred[0] if last_pred else "Low Risk"
        probability = last_pred[1] if last_pred else 0

    return render_template('result.html', prediction=prediction, probability=probability)

# ---------------- Precautions ---------------- #
@app.route('/precautions')
@login_required
def precautions_default():
    risk_level = session.get('last_prediction', 'low_risk')
    return redirect(url_for('precautions_level', risk_level=risk_level))

@app.route('/precautions/<risk_level>')
@login_required
def precautions_level(risk_level):
    precaution_dict = {
        'low_risk': [
            "Balanced diet with fruits and vegetables",
            "Light cardio exercises like walking or cycling",
            "Mental wellness activities such as meditation"
        ],
        'medium_risk': [
            "Reduce intake of processed foods and sugar",
            "Moderate exercise: 30-45 mins daily",
            "Monitor blood pressure and cholesterol regularly"
        ],
        'high_risk': [
            "Follow a strict diet as advised by your doctor",
            "Consult your doctor frequently",
            "Closely monitor vitals and avoid stressful activities"
        ]
    }

    precautions = precaution_dict.get(risk_level, precaution_dict['low_risk'])
    return render_template('precautions.html', precautions=precautions, risk_level=risk_level)

# ---------------- Medicines ---------------- #
@app.route('/medicines')
@login_required
def medicines():
    risk_level = session.get('last_prediction', 'low_risk')

    medicines_dict = {
        'low_risk': [
            {"name": "Omega-3", "purpose": "Supports heart health", "notes": "Take with meals"},
            {"name": "Multivitamins", "purpose": "General heart support", "notes": "Once daily"}
        ],
        'medium_risk': [
            {"name": "Statins", "purpose": "Lowers cholesterol", "notes": "Take in the evening"},
            {"name": "Aspirin", "purpose": "Blood thinner", "notes": "Follow doctor advice"}
        ],
        'high_risk': [
            {"name": "ACE inhibitors", "purpose": "Lower BP", "notes": "Monitor BP regularly"},
            {"name": "Beta-blockers", "purpose": "Reduces heart workload", "notes": "Consult doctor"}
        ]
    }

    medicines_list = medicines_dict.get(risk_level, medicines_dict['low_risk'])
    return render_template('medicines.html', medicines=medicines_list, risk_level=risk_level)

# ---------------- History ---------------- #
@app.route('/history')
@login_required
def history():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT prediction, probability, risk_level, timestamp FROM predictions WHERE username=? ORDER BY timestamp DESC", (session['user'],))
        history_data = cur.fetchall()
    return render_template('history.html', history=history_data)

# ---------------- Export CSV ---------------- #
@app.route('/export_csv')
@login_required
def export_csv():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT prediction, probability, risk_level, timestamp FROM predictions WHERE username=? ORDER BY timestamp DESC", conn, params=(session['user'],))
    csv_buffer = BytesIO()
    csv_buffer.write(df.to_csv(index=False).encode())
    csv_buffer.seek(0)
    return send_file(csv_buffer, mimetype='text/csv', as_attachment=True, download_name=f"{session['user']}_heart_history.csv")

# ---------------- Export PDF ---------------- #
@app.route('/export_pdf', methods=['POST'])
@login_required
def export_pdf():
    data_json = request.get_json()
    chart_data = data_json.get('chart_image') if data_json else None

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT timestamp, prediction, probability, risk_level FROM predictions WHERE username=? ORDER BY timestamp DESC", (session['user'],))
        history = cur.fetchall()

    pdf_buffer = BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width/2, height-50, f"{session['user']}'s Heart Prediction History")

    pdf.setFont("Helvetica", 12)
    y = height - 80
    pdf.drawString(50, y, "Timestamp")
    pdf.drawString(200, y, "Prediction")
    pdf.drawString(320, y, "Probability")
    pdf.drawString(420, y, "Risk Level")
    y -= 20

    for row in history:
        pdf.drawString(50, y, str(row[0]))
        pdf.drawString(200, y, str(row[1]))
        pdf.drawString(320, y, f"{row[2]}%")
        pdf.drawString(420, y, str(row[3]))
        y -= 20
        if y < 100:
            pdf.showPage()
            y = height - 50

    if chart_data:
        chart_bytes = base64.b64decode(chart_data.split(',')[1])
        chart_img = ImageReader(BytesIO(chart_bytes))
        pdf.showPage()
        pdf.drawImage(chart_img, 50, 200, width=500, height=300, preserveAspectRatio=True)

    pdf.save()
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, as_attachment=True, download_name='heart_history.pdf', mimetype='application/pdf')


# ---------------- Run App ---------------- #
if __name__ == "__main__":
    app.run(debug=True)
