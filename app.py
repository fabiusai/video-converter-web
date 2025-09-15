import os
import subprocess
import uuid
from flask import Flask, request, render_template, send_from_directory, jsonify
import requests
import m3u8

# --- Configurazione ---
# Definisce le cartelle temporanee sul server
DOWNLOAD_FOLDER = 'downloads'
CONVERTED_FOLDER = 'converted'
# Crea le cartelle se non esistono
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')

# --- Route Principale ---
@app.route('/')
def index():
    """Mostra la pagina HTML principale."""
    return render_template('index.html')

# --- API per la Conversione ---
@app.route('/process', methods=['POST'])
def process_m3u8():
    """
    API che riceve un URL M3U8, scarica i segmenti, li unisce,
    li converte con ffmpeg e restituisce un link per il download.
    """
    data = request.get_json()
    m3u8_url = data.get('url')

    if not m3u8_url:
        return jsonify({'error': 'URL M3U8 non fornito'}), 400

    # Definiamo i percorsi dei file all'inizio del blocco try
    unique_id = str(uuid.uuid4())
    ts_filename = f"{unique_id}.ts"
    mp4_filename = f"{unique_id}.mp4"
    ts_filepath = os.path.join(DOWNLOAD_FOLDER, ts_filename)
    mp4_filepath = os.path.join(CONVERTED_FOLDER, mp4_filename)

    try:
        print(f"[{unique_id}] Avvio processo per URL: {m3u8_url}")
        # 1. Carica e analizza il file M3U8
        print(f"[{unique_id}] Caricamento playlist M3U8...")
        playlist = m3u8.load(m3u8_url)
        print(f"[{unique_id}] Playlist caricata. Trovati {len(playlist.segments)} segmenti.")

        # 2. Scarica e unisce tutti i segmenti in un unico file .ts
        print(f"[{unique_id}] Inizio download segmenti su {ts_filepath}...")
        with open(ts_filepath, 'wb') as f_out:
            for i, segment in enumerate(playlist.segments):
                segment_url = segment.absolute_uri
                
                response = requests.get(segment_url, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    f_out.write(chunk)
                
                # Logga il progresso ogni 50 segmenti per non intasare i log
                if (i + 1) % 50 == 0:
                    print(f"[{unique_id}] Scaricato segmento {i+1}/{len(playlist.segments)}")

        print(f"[{unique_id}] Download segmenti completato.")
        # 3. Converte il file .ts unito in .mp4 usando ffmpeg
        print(f"[{unique_id}] Avvio conversione FFMPEG...")
        command = [
            'ffmpeg',
            '-i', ts_filepath,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-y',
            mp4_filepath
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"[{unique_id}] Conversione FFMPEG completata.")

        # 4. Restituisce l'URL per scaricare il file convertito
        return jsonify({'download_url': f'/download/{mp4_filename}'})

    except subprocess.CalledProcessError as e:
        print(f"Errore FFMPEG: {e.stderr}")
        return jsonify({'error': f"Errore durante la conversione video: {e.stderr}"}), 500
    except Exception as e:
        print(f"Errore generico: {e}")
        return jsonify({'error': f"Si è verificato un errore: {str(e)}"}), 500
    finally:
        if os.path.exists(ts_filepath):
            os.remove(ts_filepath)

# --- Route per il Download ---
@app.route('/download/<filename>')
def download_file(filename):
    """Permette al browser di scaricare il file convertito."""
    return send_from_directory(CONVERTED_FOLDER, filename, as_attachment=True)

