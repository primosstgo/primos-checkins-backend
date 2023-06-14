FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /django
COPY . /django
RUN pip3 install -r requirements.txt --no-cache-dir
