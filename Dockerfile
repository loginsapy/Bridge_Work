FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=run.py
CMD ["gunicorn", "run:app", "-b", "0.0.0.0:8000"]
