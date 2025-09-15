# 1. Partiamo da un'immagine ufficiale Python leggera
FROM python:3.11-slim

# 2. Impostiamo una directory di lavoro dentro il nostro "mini-computer"
WORKDIR /app

# 3. Aggiorniamo la lista dei pacchetti e installiamo ffmpeg (qui possiamo farlo!)
RUN apt-get update && apt-get install -y ffmpeg

# 4. Copiamo il file delle dipendenze Python
COPY requirements.txt .

# 5. Installiamo le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiamo tutto il resto della nostra applicazione
COPY . .

# 7. Diciamo a Render su quale porta il nostro server sarà in ascolto
# Render si aspetta la porta 10000 per i servizi Docker
EXPOSE 10000

# 8. Definiamo il comando per avviare l'applicazione quando il server parte
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
