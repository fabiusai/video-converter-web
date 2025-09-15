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
    Eseguita in background per pulire i file e i job più vecchi di 30 minuti.
    """
    while True:
        try:
            print("[CLEANUP] Esecuzione della pulizia...")
            now = time.time()
            expiration_time = 1800  # Durata in secondi (30 minuti)
            
            job_ids_to_check = list(jobs.keys())

            for job_id in job_ids_to_check:
                job = jobs.get(job_id)
                if job and 'created_at' in job and (now - job['created_at'] > expiration_time):
                    print(f"[CLEANUP] Il Job {job_id} è scaduto. Pulizia in corso...")
                    
                    mp4_filename = f"{job_id}.mp4"
                    mp4_filepath = os.path.join(CONVERTED_FOLDER, mp4_filename)
                    if os.path.exists(mp4_filepath):
                        os.remove(mp4_filepath)
                        print(f"[CLEANUP] File eliminato: {mp4_filepath}")
                    
                    del jobs[job_id]
                    print(f"[CLEANUP] Job rimosso dalla memoria: {job_id}")

        except Exception as e:
            print(f"[CLEANUP] Errore durante la pulizia: {e}")
        
        time.sleep(300) # Aspetta 5 minuti

def run_conversion_task(job_id, m3u8_url, audio_delay_cs):
    ts_filename = f"{job_id}.ts"
    mp4_filename = f"{job_id}.mp4"
    ts_filepath = os.path.join(DOWNLOAD_FOLDER, ts_filename)
    mp4_filepath = os.path.join(CONVERTED_FOLDER, mp4_filename)

    try:
        jobs[job_id]['status'] = 'downloading'
        playlist = m3u8.load(m3u8_url)

        with open(ts_filepath, 'wb') as f_out:
            for segment in playlist.segments:
                response = requests.get(segment.absolute_uri, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    f_out.write(chunk)
        
        jobs[job_id]['status'] = 'converting'
        
        # --- LOGICA FFMPEG CON CONTROLLO DEL RITARDO AUDIO ---
        command = ['ffmpeg', '-i', ts_filepath]

        # Se è specificato un ritardo, l'audio deve essere ricodificato.
        if audio_delay_cs != 0:
            delay_in_seconds = float(audio_delay_cs) / 100.0
            print(f"[FFMPEG] Applicazione di un ritardo audio di {delay_in_seconds} secondi.")
            # Copia il video, ma applica un filtro all'audio
            command.extend([
                '-c:v', 'copy',
                '-af', f'asetpts=PTS+({delay_in_seconds})/TB' 
            ])
        else:
            # Conversione lossless standard
            command.extend([
                '-c', 'copy',
                '-copyts',
                '-start_at_zero',
                '-bsf:a', 'aac_adtstoasc'
            ])
        
        command.extend(['-y', mp4_filepath])

        subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)

        jobs[job_id].update({
            'status': 'complete',
            'download_url': f'/download/{mp4_filename}'
        })
    except Exception as e:
        error_message = str(e)
        if hasattr(e, 'stderr'):
            error_message = e.stderr
        jobs[job_id].update({'status': 'error', 'message': error_message})
    finally:
        if os.path.exists(ts_filepath):
            os.remove(ts_filepath)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_m3u8():
    data = request.get_json()
    m3u8_url = data.get('url')
    audio_delay_cs = data.get('audio_delay', 0) # Riceve il valore del ritardo

    if not m3u8_url:
        return jsonify({'error': 'URL M3U8 non fornito'}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'starting', 'created_at': time.time()}
    
    # Passa il ritardo al thread di conversione
    thread = threading.Thread(target=run_conversion_task, args=(job_id, m3u8_url, audio_delay_cs))
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job non trovato o scaduto.'}), 404
    return jsonify(job)

@app.route('/download/<filename>')
def download_file(filename):
    filepath = os.path.join(CONVERTED_FOLDER, filename)
    if not os.path.exists(filepath):
        return "<h1>Errore: File non trovato.</h1><p>Il link per il download potrebbe essere scaduto (dura circa 30 minuti) o il server potrebbe essere stato riavviato. Per favore, prova a riconvertire il video.</p>", 404
    return send_from_directory(CONVERTED_FOLDER, filename, as_attachment=True)

if __name__ != '__main__':
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    print("Thread di pulizia per i file e i job vecchi avviato.")

