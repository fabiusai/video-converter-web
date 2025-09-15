import os
import subprocess
import uuid
from flask import Flask, request, render_template, send_from_directory, jsonify
import requests
import m3u8
import threading
import time
import glob

# --- Configurazione ---
DOWNLOAD_FOLDER = 'downloads'
CONVERTED_FOLDER = 'converted'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')

# --- "Database" in memoria per i lavori ---
jobs = {}

# --- Funzione di Pulizia in Background ---
def cleanup_old_files():
    """
    Eseguita in un thread separato per pulire periodicamente i file convertiti
    più vecchi di 1 ora, per liberare spazio su disco.
    """
    while True:
        try:
            print("[CLEANUP] Esecuzione della pulizia dei vecchi file...")
            now = time.time()
            # Cerca tutti i file .mp4 nella cartella dei file convertiti
            for filepath in glob.glob(os.path.join(CONVERTED_FOLDER, '*.mp4')):
                # Se il file è più vecchio di 3600 secondi (1 ora), eliminalo
                if os.path.getmtime(filepath) < now - 3600:
                    os.remove(filepath)
                    print(f"[CLEANUP] File eliminato perché obsoleto: {filepath}")
        except Exception as e:
            print(f"[CLEANUP] Errore durante la pulizia: {e}")
        
        # Aspetta 1 ora prima di eseguire di nuovo la pulizia
        time.sleep(3600)

def run_conversion_task(job_id, m3u8_url):
    """
    Contiene la logica di download e conversione, eseguita in background.
    """
    ts_filename = f"{job_id}.ts"
    mp4_filename = f"{job_id}.mp4"
    ts_filepath = os.path.join(DOWNLOAD_FOLDER, ts_filename)
    mp4_filepath = os.path.join(CONVERTED_FOLDER, mp4_filename)

    try:
        jobs[job_id]['status'] = 'downloading'
        print(f"[{job_id}] Caricamento playlist M3U8...")
        playlist = m3u8.load(m3u8_url)
        print(f"[{job_id}] Trovati {len(playlist.segments)} segmenti.")

        with open(ts_filepath, 'wb') as f_out:
            for i, segment in enumerate(playlist.segments):
                segment_url = segment.absolute_uri
                response = requests.get(segment_url, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    f_out.write(chunk)
                if (i + 1) % 50 == 0:
                    print(f"[{job_id}] Scaricato segmento {i+1}/{len(playlist.segments)}")

        jobs[job_id]['status'] = 'converting'
        print(f"[{job_id}] Avvio conversione FFMPEG...")
        command = [
            'ffmpeg', '-i', ts_filepath, '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc', '-y', mp4_filepath
        ]
        # Aggiunto un timeout al processo ffmpeg per sicurezza
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)

        jobs[job_id].update({
            'status': 'complete',
            'download_url': f'/download/{mp4_filename}'
        })
        print(f"[{job_id}] Conversione completata.")

    except subprocess.CalledProcessError as e:
        print(f"[{job_id}] Errore FFMPEG: {e.stderr}")
        jobs[job_id].update({'status': 'error', 'message': f"Errore FFMPEG: {e.stderr}"})
    except Exception as e:
        print(f"[{job_id}] Errore durante il processo: {e}")
        jobs[job_id].update({'status': 'error', 'message': str(e)})
    finally:
        if os.path.exists(ts_filepath):
            os.remove(ts_filepath)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_m3u8():
    m3u8_url = request.get_json().get('url')
    if not m3u8_url:
        return jsonify({'error': 'URL M3U8 non fornito'}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'starting'}
    
    thread = threading.Thread(target=run_conversion_task, args=(job_id, m3u8_url))
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job non trovato'}), 404
    return jsonify(job)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(CONVERTED_FOLDER, filename, as_attachment=True)

# --- Avvio del Thread di Pulizia ---
# Questo codice viene eseguito solo quando l'app parte su Render (non in locale)
if __name__ != '__main__':
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    print("Thread di pulizia per i file vecchi avviato.")

