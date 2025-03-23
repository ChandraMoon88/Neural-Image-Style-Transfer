from flask import Flask, render_template, request, send_file, url_for, Response, jsonify
from PIL import Image
import numpy as np
from io import BytesIO
from API import transfer_style
import os
import cv2
import traceback
import base64

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Global variables for storing captured images
content_image = None
style_image = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def process_image(image):
    # Convert to RGB if necessary
    if len(image.shape) == 2:  # grayscale
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:  # RGBA
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    
    # Resize if necessary
    height, width = image.shape[:2]
    max_size = 1000
    if height > max_size or width > max_size:
        scale = max_size / max(height, width)
        image = cv2.resize(image, None, fx=scale, fy=scale)
    
    return image

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_files', methods=['POST'])
def upload_files():
    global content_image, style_image
    
    try:
        if 'content_image' not in request.files or 'style_image' not in request.files:
            return render_template('index.html', error='Please upload both content and style images.')
        
        content_file = request.files['content_image']
        style_file = request.files['style_image']
        
        if content_file.filename == '' or style_file.filename == '':
            return render_template('index.html', error='No selected files')
            
        if not (allowed_file(content_file.filename) and allowed_file(style_file.filename)):
            return render_template('index.html', error='Invalid file type. Please upload PNG, JPG, or GIF files.')
            
        # Process content image
        content_image_data = content_file.read()
        content_array = np.frombuffer(content_image_data, np.uint8)
        content_image = cv2.imdecode(content_array, cv2.IMREAD_COLOR)
        content_image = process_image(content_image)
        cv2.imwrite(os.path.join(app.config['UPLOAD_FOLDER'], 'content.jpg'), content_image)
        
        # Process style image
        style_image_data = style_file.read()
        style_array = np.frombuffer(style_image_data, np.uint8)
        style_image = cv2.imdecode(style_array, cv2.IMREAD_COLOR)
        style_image = process_image(style_image)
        cv2.imwrite(os.path.join(app.config['UPLOAD_FOLDER'], 'style.jpg'), style_image)
        
        # Perform style transfer
        model_path = "model"
        styled_image = transfer_style(content_image, style_image, model_path)
        styled_image = (styled_image * 255).astype(np.uint8)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.jpg')
        cv2.imwrite(output_path, cv2.cvtColor(styled_image, cv2.COLOR_RGB2BGR))
        
        return render_template('result.html', 
                             content_image=url_for('static', filename='uploads/content.jpg'),
                             style_image=url_for('static', filename='uploads/style.jpg'),
                             output_image=url_for('static', filename='uploads/output.jpg'))
                             
    except Exception as e:
        return render_template('index.html', error=f'An error occurred: {str(e)}')

@app.route('/capture_content')
def capture_content():
    return render_template('capture.html', mode='content')

@app.route('/capture_style')
def capture_style():
    return render_template('capture.html', mode='style')

def gen_frames(camera):
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    camera = cv2.VideoCapture(0)
    return Response(gen_frames(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/capture', methods=['POST'])
def capture():
    global content_image, style_image
    
    try:
        mode = request.form['mode']
        image_data = request.form['image'].split(',')[1]
        image_array = np.frombuffer(base64.b64decode(image_data), np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        
        processed_image = process_image(image)
        
        if mode == 'content':
            content_image = processed_image
            cv2.imwrite(os.path.join(app.config['UPLOAD_FOLDER'], 'content.jpg'), content_image)
        else:
            style_image = processed_image
            cv2.imwrite(os.path.join(app.config['UPLOAD_FOLDER'], 'style.jpg'), style_image)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/transfer', methods=['POST'])
def transfer():
    global content_image, style_image
    
    try:
        if content_image is None or style_image is None:
            return render_template('index.html', error='Please capture both content and style images.')
        
        model_path = "model"
        styled_image = transfer_style(content_image, style_image, model_path)
        
        # Save the styled image
        styled_image = (styled_image * 255).astype(np.uint8)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.jpg')
        cv2.imwrite(output_path, cv2.cvtColor(styled_image, cv2.COLOR_RGB2BGR))
        
        return render_template('result.html', 
                             content_image=url_for('static', filename='uploads/content.jpg'),
                             style_image=url_for('static', filename='uploads/style.jpg'),
                             output_image=url_for('static', filename='uploads/output.jpg'))
    except Exception as e:
        return render_template('index.html', error=f'An error occurred: {str(e)}')

@app.route('/download')
def download():
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.jpg')
    return send_file(output_path, as_attachment=True, download_name='styled_image.jpg')

if __name__ == '__main__':
    app.run(debug=True)