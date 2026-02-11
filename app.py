import os
from flask import Flask, request, send_file, render_template, jsonify
from PIL import Image
import subprocess
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB limit

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/resize-image", methods=["POST"])
def resize_image():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    width = int(request.form.get("width", 500))
    height = int(request.form.get("height", 500))

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, "resized_" + filename)

    file.save(input_path)

    try:
        img = Image.open(input_path)
        img = img.resize((width, height))
        img.save(output_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return send_file(output_path, as_attachment=True)


@app.route("/resize-video", methods=["POST"])
def resize_video():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    width = request.form.get("width", "640")
    height = request.form.get("height", "480")

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, "resized_" + filename)

    file.save(input_path)

    command = [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"scale={width}:{height}",
        "-y",
        output_path
    ]

    try:
        subprocess.run(command, check=True, timeout=120)
    except subprocess.CalledProcessError:
        return jsonify({"error": "FFmpeg failed"}), 500

    return send_file(output_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
