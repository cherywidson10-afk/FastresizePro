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
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sklearn.ensemble import RandomForestClassifier

# ================= CONFIG =================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "super-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///fastresize.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

FREE_LIMIT = 10
MODEL_PATH = "ml_model.pkl"

db = SQLAlchemy(app)
login_manager = LoginManager(app)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ================= HOME ROUTE (FIX NOT FOUND) =================

@app.route("/")
def home():
    return """
    <h1>🚀 FastResize Pro API</h1>
    <p>Server is running successfully ✅</p>
    <p>Available endpoints:</p>
    <ul>
        <li>/register</li>
        <li>/login</li>
        <li>/verify-otp</li>
        <li>/dashboard</li>
        <li>/resize-video</li>
        <li>/paypal-webhook</li>
    </ul>
    """

# ================= DATABASE =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    resize_count = db.Column(db.Integer, default=0)
    fraud_score = db.Column(db.Integer, default=0)
    is_premium = db.Column(db.Boolean, default=False)
    subscription_expiry = db.Column(db.DateTime)
    is_permanent_ban = db.Column(db.Boolean, default=False)
    ban_until = db.Column(db.DateTime)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ================= ML MODEL =================

def train_model():
    X = np.array([[5,0],[20,10],[50,80],[100,150]])
    y = np.array([0,0,1,1])
    model = RandomForestClassifier()
    model.fit(X,y)
    joblib.dump(model, MODEL_PATH)

if not os.path.exists(MODEL_PATH):
    train_model()

model = joblib.load(MODEL_PATH)

def ml_detect(user):
    features = np.array([[user.resize_count, user.fraud_score]])
    return model.predict(features)[0] == 1

# ================= AUTH =================

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email exists"}), 400

    user = User(
        email=data["email"],
        password=generate_password_hash(data["password"])
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Registered successfully"})

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(email=data["email"]).first()

    if not user or not check_password_hash(user.password, data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401

    login_user(user)
    return jsonify({"message": "Login successful"})

# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    remaining = "Unlimited" if current_user.is_premium else max(0, FREE_LIMIT - current_user.resize_count)
    return jsonify({
        "email": current_user.email,
        "premium": current_user.is_premium,
        "resize_used": current_user.resize_count,
        "resize_remaining": remaining,
        "fraud_score": current_user.fraud_score
    })

# ================= RESIZE =================

@app.route("/resize-video", methods=["POST"])
@login_required
def resize_video():

    if not current_user.is_premium and current_user.resize_count >= FREE_LIMIT:
        return jsonify({"error": "Free limit reached"}), 403

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    width = int(request.form.get("width", 640))
    height = int(request.form.get("height", 480))

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, f"{uuid.uuid4()}.mp4")

    file.save(input_path)

    try:
        subprocess.run(
            ["ffmpeg", "-i", input_path, "-vf", f"scale={width}:{height}", "-y", output_path],
            check=True
        )
    except:
        return jsonify({"error": "Video processing failed"}), 500

    current_user.resize_count += 1
    db.session.commit()

    return send_file(output_path, as_attachment=True)

# ================= INIT =================

with app.app_context():
    db.create_all()
