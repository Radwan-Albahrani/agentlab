# Base image for companions: Python + the template's dependencies + the launcher. The code is NOT in the image: it is
# the owner's agent's checkout, mounted read-only at /app (see base/run.py). Build from this folder:
#   docker build -t agentlab/companion .
FROM python:3.13-slim
COPY requirements.txt /etc/companion/requirements.txt
RUN pip install --no-cache-dir -r /etc/companion/requirements.txt \
 && sha256sum /etc/companion/requirements.txt | cut -d' ' -f1 > /etc/companion/requirements.sha256
COPY --chmod=755 base/run.py /usr/local/lib/companion/run.py
RUN python3 -m compileall -q /usr/local/lib/companion
ENV PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
WORKDIR /app
CMD ["python3", "-u", "/usr/local/lib/companion/run.py"]
