FROM mirror.gcr.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QT_X11_NO_MITSHM=1 \
    DEBIAN_FRONTEND=noninteractive

# Системные библиотеки, нужные PyQt5/QtCharts для отрисовки
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 libegl1 libxkbcommon0 libdbus-1-3 \
        libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
        libxcb-render-util0 libxcb-shape0 libxcb-sync1 libxcb-xfixes0 \
        libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 \
        libfontconfig1 libxrender1 libsm6 libxext6 \
        libpulse0 libnss3 libasound2 \
        libcups2 \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY sql/ ./sql/

CMD ["python", "app/main.py"]
