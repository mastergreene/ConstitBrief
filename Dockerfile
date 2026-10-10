FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY frontend frontend
ENV HOST=0.0.0.0 PORT=8787 DB_PATH=/data/constitbrief.sqlite3
VOLUME /data
EXPOSE 8787
CMD ["python", "-m", "backend.app.main"]
