import os
from flask import Flask, request, send_file, jsonify
from PIL import Image
import subprocess

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Home route
@app.route("/")
def home():
    return "Video & Image Resizer API is running 🚀"

# IMAGE RESIZE
@app.route("/resize-image", methods=["POST"])
def resize_image():
    file = request.files["file"]
    width = int(request.form["width"])
    height = int(request.form["height"])

    input_path = os.path.join(UPLOAD_FOLDER, file.filename)
    output_path = os.path.join(OUTPUT_FOLDER, "resized_" + file.filename)

    file.save(input_path)

    img = Image.open(input_path)
    img = img.resize((width, height))
    img.save(output_path)

    return send_file(output_path, as_attachment=True)

# VIDEO RESIZE
@app.route("/resize-video", methods=["POST"])
def resize_video():
    file = request.files["file"]
    width = request.form["width"]
    height = request.form["height"]

    input_path = os.path.join(UPLOAD_FOLDER, file.filename)
    output_path = os.path.join(OUTPUT_FOLDER, "resized_" + file.filename)

    file.save(input_path)

    command = [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"scale={width}:{height}",
        output_path
    ]

    subprocess.run(command)

    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
