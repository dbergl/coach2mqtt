FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY winegard2mqtt/ ./winegard2mqtt/

RUN useradd --create-home --uid 1000 app
USER app

CMD ["python3", "-u", "-m", "winegard2mqtt.app"]
