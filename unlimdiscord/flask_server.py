from flask import Flask, render_template, request, jsonify, send_file
import os
import requests
import uuid
import json
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
CHUNK_SIZE = 24 * 1024 * 1024  # 24 Mo
FILE_DATABASE = 'files.json'
DOWNLOAD_FOLDER = 'downloads/'

# Chargement des fichiers existants à partir de la base de données
if os.path.exists(FILE_DATABASE):
    with open(FILE_DATABASE, 'r') as f:
        uploaded_files = json.load(f)
else:
    uploaded_files = {}

# Sauvegarder l'état des fichiers uploadés
def save_uploaded_files():
    with open(FILE_DATABASE, 'w') as f:
        json.dump(uploaded_files, f)

# Fonction pour uploader un fichier via le webhook Discord
def upload_to_discord(file, webhook_url):
    files = {'file': file}
    response = requests.post(webhook_url, files=files)
    if response.status_code == 200:
        # Retourne l'URL du fichier uploadé
        return response.json()['attachments'][0]['url']
    return None

# Page d'accueil avec formulaire pour uploader
@app.route('/')
def index():
    return render_template('index.html', files=uploaded_files)

# Route pour uploader les fichiers
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files or 'webhook_url' not in request.form:
        return jsonify({"error": "No file or webhook URL provided"}), 400
    
    file = request.files['file']
    webhook_url = request.form['webhook_url']

    if file:
        file_id = str(uuid.uuid4())  # Génère un identifiant unique pour ce fichier
        filename = secure_filename(file.filename)
        file_size = file.content_length

        # Split and upload
        chunk_urls = []
        chunk_number = 0
        while True:
            chunk = file.stream.read(CHUNK_SIZE)
            if not chunk:
                break
            chunk_filename = f"{file_id}_part{chunk_number}"
            chunk_url = upload_to_discord((chunk_filename, chunk), webhook_url)
            if chunk_url:
                chunk_urls.append(chunk_url)
                chunk_number += 1
            else:
                return jsonify({"error": "Failed to upload chunk"}), 500

        # Sauvegarder les informations du fichier
        uploaded_files[file_id] = {
            "filename": filename,
            "chunk_urls": chunk_urls
        }
        save_uploaded_files()
        
        return jsonify({"message": "File uploaded successfully", "file_id": file_id, "chunks": chunk_urls}), 200

# Fonction pour télécharger et assembler les fichiers
def download_and_reconstruct_file(chunk_urls, file_id, original_filename):
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    reconstructed_file_path = os.path.join(DOWNLOAD_FOLDER, original_filename)
    
    with open(reconstructed_file_path, 'wb') as output_file:
        for url in chunk_urls:
            response = requests.get(url)
            output_file.write(response.content)
    return reconstructed_file_path

# Route pour télécharger les fichiers
@app.route('/download', methods=['POST'])
def download_file():
    data = request.json
    file_id = data.get('file_id')

    if not file_id or file_id not in uploaded_files:
        return jsonify({"error": "Invalid file ID"}), 400

    file_info = uploaded_files[file_id]
    reconstructed_file_path = download_and_reconstruct_file(file_info['chunk_urls'], file_id, file_info['filename'])
    
    return send_file(reconstructed_file_path, as_attachment=True, download_name=file_info['filename'])

# Route pour supprimer un fichier de la liste (ne supprime pas les fichiers sur Discord)
@app.route('/delete', methods=['POST'])
def delete_file():
    data = request.json
    file_id = data.get('file_id')

    if not file_id or file_id not in uploaded_files:
        return jsonify({"error": "Invalid file ID"}), 400

    del uploaded_files[file_id]
    save_uploaded_files()
    
    return jsonify({"message": "File deleted successfully"}), 200

if __name__ == '__main__':
    app.run(debug=True)
