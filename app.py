import os
import uuid
import random
import hashlib
import datetime
import subprocess
import joblib
import numpy as np

from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sklearn.ensemble import RandomForestClassifier

# ================= CONFIG =================

app = Flask(__name__)
app.config["SECRET_KEY"] = "CHANGE_THIS_SECRET"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fastresize.db"

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "YOUR_GMAIL@gmail.com"
app.config["MAIL_PASSWORD"] = "YOUR_APP_PASSWORD"

FREE_LIMIT = 10
AI_AUTO_ADMIN = True
MODEL_PATH = "ml_model.pkl"

db = SQLAlchemy(app)
login_manager = LoginManager(app)
mail = Mail(app)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ================= DATABASE =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))

    resize_count = db.Column(db.Integer, default=0)
    fraud_score = db.Column(db.Integer, default=0)

    is_premium = db.Column(db.Boolean, default=False)
    subscription_expiry = db.Column(db.DateTime)

    is_suspended = db.Column(db.Boolean, default=False)
    ban_until = db.Column(db.DateTime)
    is_permanent_ban = db.Column(db.Boolean, default=False)

    otp_code = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
    is_verified = db.Column(db.Boolean, default=False)

    device_hash = db.Column(db.String(128))
    last_ip = db.Column(db.String(100))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= UTILITIES =================

def generate_fingerprint(req):
    raw = req.headers.get("User-Agent", "") + req.remote_addr
    return hashlib.sha256(raw.encode()).hexdigest()

def generate_otp():
    return str(random.randint(100000, 999999))

def send_email(subject, body, recipient):
    msg = Message(subject=subject,
                  sender=app.config["MAIL_USERNAME"],
                  recipients=[recipient])
    msg.body = body
    mail.send(msg)

def check_ban(user):
    if user.is_permanent_ban:
        return "Permanent ban"
    if user.ban_until and datetime.datetime.utcnow() < user.ban_until:
        return f"Temporary ban until {user.ban_until}"
    return None

# ================= ML MODEL =================

def train_model():
    X = np.array([
        [5, 0], [10, 10], [20, 30], [50, 80], [100, 150]
    ])
    y = np.array([0, 0, 1, 1, 1])
    model = RandomForestClassifier()
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)

if not os.path.exists(MODEL_PATH):
    train_model()

model = joblib.load(MODEL_PATH)

def ml_detect(user):
    features = np.array([[user.resize_count, user.fraud_score]])
    prediction = model.predict(features)
    return prediction[0] == 1

# ================= FRAUD ENGINE =================

def evaluate_risk(user, score_add, reason):
    user.fraud_score += score_add

    if user.fraud_score >= 150:
        user.is_permanent_ban = True
        send_email("Account Permanently Banned",
                   f"Your account was permanently banned.\nReason: {reason}",
                   user.email)

    elif user.fraud_score >= 80:
        user.ban_until = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        send_email("30 Day Ban",
                   f"Your account was suspended 30 days.\nReason: {reason}",
                   user.email)

    elif user.fraud_score >= 50:
        user.ban_until = datetime.datetime.utcnow() + datetime.timedelta(days=15)

    elif user.fraud_score >= 30:
        user.ban_until = datetime.datetime.utcnow() + datetime.timedelta(days=5)

    db.session.commit()

# ================= AUTH =================

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    fingerprint = generate_fingerprint(request)

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email exists"}), 400

    user = User(
        email=data["email"],
        password=generate_password_hash(data["password"]),
        device_hash=fingerprint,
        last_ip=request.remote_addr
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "Registered"})

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(email=data["email"]).first()

    if not user or not check_password_hash(user.password, data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401

    ban_status = check_ban(user)
    if ban_status:
        return jsonify({"error": ban_status}), 403

    user.otp_code = generate_otp()
    user.otp_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    db.session.commit()

    send_email("Your OTP Code",
               f"Your login code is: {user.otp_code}",
               user.email)

    return jsonify({"message": "OTP sent"})

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.json
    user = User.query.filter_by(email=data["email"]).first()

    if user.otp_code != data["otp"]:
        return jsonify({"error": "Invalid OTP"}), 400

    if datetime.datetime.utcnow() > user.otp_expiry:
        return jsonify({"error": "OTP expired"}), 400

    login_user(user)
    return jsonify({"message": "Login successful"})

# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    return jsonify({
        "email": current_user.email,
        "premium": current_user.is_premium,
        "resize_used": current_user.resize_count,
        "resize_remaining": "Unlimited" if current_user.is_premium else FREE_LIMIT - current_user.resize_count,
        "fraud_score": current_user.fraud_score
    })

# ================= RESIZE =================

@app.route("/resize-video", methods=["POST"])
@login_required
def resize_video():

    ban_status = check_ban(current_user)
    if ban_status:
        return jsonify({"error": ban_status}), 403

    if not current_user.is_premium:
        if current_user.resize_count >= FREE_LIMIT:
            return jsonify({"error": "Free limit reached"}), 403

    file = request.files.get("file")
    width = int(request.form.get("width", 640))
    height = int(request.form.get("height", 480))

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, f"fastresizePro-{uuid.uuid4()}.mp4")

    file.save(input_path)

    filter_value = f"scale={width}:{height}"
    if not current_user.is_premium:
        filter_value += ",drawtext=text='fastresizePro':fontcolor=white:fontsize=24:x=10:y=10"

    command = ["ffmpeg", "-i", input_path, "-vf", filter_value, "-y", output_path]
    subprocess.run(command)

    current_user.resize_count += 1

    if ml_detect(current_user):
        evaluate_risk(current_user, 30, "ML Fraud Pattern")

    db.session.commit()

    return send_file(output_path, as_attachment=True)

# ================= PAYPAL WEBHOOK =================

@app.route("/paypal-webhook", methods=["POST"])
def paypal_webhook():
    data = request.json
    email = data.get("email")
    plan = data.get("plan")

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if plan == "monthly":
        user.is_premium = True
        user.subscription_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=30)

    elif plan == "yearly":
        user.is_premium = True
        user.subscription_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=365)

    elif plan == "lifetime":
        user.is_premium = True
        user.subscription_expiry = None

    db.session.commit()

    send_email("Payment Received",
               f"Your {plan} subscription is active.",
               user.email)

    return jsonify({"status": "ok"})

# ================= MAIN =================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
