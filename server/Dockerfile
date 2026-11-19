FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# ffmpeg re-encodes uploaded songs to one standard format (CBR MP3, 44.1 kHz) so
# every browser, Safari included, can seek and sync them accurately.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
