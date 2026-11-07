FROM python:3.12-slim

ENV PYTHONIOENCODING=utf-8

# Copy the two requirements files first, then install, to leverage Docker layer
# caching: when dependencies are unchanged this layer is reused (no reinstall).
COPY backend/requirements.txt /tmp/requirements/backend.txt
COPY ppt-master/skills/ppt-master/requirements.txt /tmp/requirements/ppt-master.txt

# Install backend + PPT Master deps into a single interpreter in one resolve so
# overlapping pins are reconciled (pillow==12.3.0 vs Pillow>=9.0.0,
# python-pptx==1.0.2 vs >=0.6.21). All deps have prebuilt manylinux wheels for
# cp312 / abi3, so no compiler or apt system libraries are required.
RUN pip install --no-cache-dir \
    -r /tmp/requirements/backend.txt \
    -r /tmp/requirements/ppt-master.txt

# CJK fonts: Chinese PDF/PPT export falls back to Helvetica (garbled output)
# without a real CJK typeface installed in the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Application code
COPY backend/ /app/backend/
COPY ppt-master/ /opt/ppt-master/

# Runtime env: writable data dir + PPT Master reuses the same system interpreter.
# First boot is self-initializing: app.core.config creates DATA_DIR, auto-generates
# MASTER_KEY into $LUMO_DATA_DIR/.env, and app.main._bootstrap_schema does
# create_all + stamp alembic head on a fresh DB (no explicit alembic upgrade needed).
ENV LUMO_DATA_DIR=/data \
    PPT_MASTER_HOME=/opt/ppt-master \
    PPT_MASTER_PYTHON=/usr/local/bin/python

RUN mkdir -p /data

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
