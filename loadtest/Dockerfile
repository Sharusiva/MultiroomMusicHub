FROM python:3.11-slim
RUN pip install --no-cache-dir "python-socketio[asyncio_client]==5.11.4" "aiohttp==3.10.10"
COPY loadtest.py /loadtest.py
ENTRYPOINT ["python", "/loadtest.py"]
