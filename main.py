from flask import Flask, jsonify, render_template, send_file, request, session
import os
from io import BytesIO
import zipfile
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import uuid
import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.utils import cloudinary_url
from dotenv import load_dotenv
import requests
import datetime
import time

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

# Constants
WHITEBOARD_SIZE = (864, 576)  # PDF page size (12x8 inches at 72 DPI)
CLOUDINARY_FOLDER = "whiteboard_captures"  # Folder in Cloudinary to store images

# User session data
user_deleted_images = {}  # Track deletions per user session

# Assign a unique session ID on first request
@app.before_request
def init_user_session():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        user_deleted_images[session['user_id']] = set()

# Serve the main page
@app.route('/')
def index():
    return render_template('index.html')

# API: Delete an image for the current user (soft delete by tracking in session)
@app.route('/api/delete/<public_id>', methods=['DELETE'])
def delete_image(public_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "No session"}), 401
    
    # Store the deleted image ID in the user's session
    user_deleted_images[user_id].add(public_id)
    return jsonify({"message": "Deleted"})

# API: List non-deleted images for the current user (sorted by timestamp)
@app.route('/api/images')
def list_images():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "No session"}), 401

    # Get images from Cloudinary
    try:
        result = cloudinary.api.resources(
            type="upload",
            prefix=CLOUDINARY_FOLDER + "/",
            max_results=500,
            metadata=True
        )
        
        # Filter and format image list
        image_list = []
        for resource in result.get('resources', []):
            public_id = resource['public_id']
            filename = public_id.split('/')[-1]
            
            # Skip deleted images
            if public_id in user_deleted_images.get(user_id, set()):
                continue
                
            # Use created_at as timestamp
            timestamp = resource.get('created_at', '')
            # Convert string timestamp to unix timestamp
            if timestamp:
                # Parse the ISO format timestamp
                dt = datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S%z')
                unix_timestamp = dt.timestamp()
            else:
                unix_timestamp = 0
                
            image_list.append({
                "filename": filename,
                "public_id": public_id,
                "url": resource['secure_url'],
                "timestamp": unix_timestamp
            })
        
        # Sort by timestamp ascending (oldest -> newest)
        sorted_images = sorted(image_list, key=lambda x: x['timestamp'])
        
        return jsonify(sorted_images)
    
    except Exception as e:
        print(f"Error fetching images from Cloudinary: {e}")
        return jsonify({"error": str(e)}), 500

# API: Serve an image (using Cloudinary URL)
@app.route('/api/images/<public_id>')
def get_image(public_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "No session"}), 401
    
    if public_id in user_deleted_images.get(user_id, set()):
        return jsonify({"error": "Not available"}), 404
    
    # Get the Cloudinary URL and redirect to it
    try:
        url, options = cloudinary_url(public_id)
        return jsonify({"url": url}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Download all non-deleted images as ZIP
@app.route('/api/download')
def download_all():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "No session"}), 401
    
    try:
        # Get the list of images (reusing list_images logic)
        response = list_images()
        if response.status_code != 200:
            return response
        
        image_list = response.json
        
        # Create ZIP with images in the correct order
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as zip_file:
            for i, img in enumerate(image_list):
                # Download the image from Cloudinary
                image_response = requests.get(img['url'])
                if image_response.status_code == 200:
                    # Use a numbered filename to preserve order
                    filename = f"{i+1:03d}_{img['filename']}"
                    zip_file.writestr(filename, image_response.content)
                
        buffer.seek(0)
        return send_file(buffer, mimetype='application/zip', as_attachment=True, download_name='whiteboard_images.zip')
    
    except Exception as e:
        print(f"Error creating ZIP: {e}")
        return jsonify({"error": str(e)}), 500

# API: Generate a PDF with all non-deleted images (one per page)
@app.route('/api/download-pdf')
def download_pdf():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "No session"}), 401
    
    try:
        # Get the list of images (reusing list_images logic)
        response = list_images()
        if response.status_code != 200:
            return response
            
        image_list = response.json
        
        # Generate PDF with images in the correct order
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=WHITEBOARD_SIZE)
        
        for img in image_list:
            # Download the image from Cloudinary
            image_response = requests.get(img['url'])
            if image_response.status_code == 200:
                # Create a BytesIO object from the image content
                image_buffer = BytesIO(image_response.content)
                # Draw the image on the PDF
                pdf.drawImage(ImageReader(image_buffer), 0, 0, *WHITEBOARD_SIZE)
                pdf.showPage()  # New page
                
        pdf.save()
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='whiteboard_images.pdf')
    
    except Exception as e:
        print(f"Error creating PDF: {e}")
        return jsonify({"error": str(e)}), 500

# API: Upload a new image (for testing without Raspberry Pi)
@app.route('/api/upload', methods=['POST'])
def upload_image():
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    # If user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        try:
            # Generate a timestamp for the filename
            timestamp = int(time.time())
            filename = f"{timestamp}_{file.filename}"
            
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file,
                folder=CLOUDINARY_FOLDER,
                public_id=filename,
                resource_type="image"
            )
            
            return jsonify({
                "message": "Upload successful",
                "public_id": upload_result['public_id'],
                "url": upload_result['secure_url']
            })
        except Exception as e:
            print(f"Error uploading to Cloudinary: {e}")
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "Failed to upload file"}), 500

if __name__ == '__main__':
    app.run(debug=True)