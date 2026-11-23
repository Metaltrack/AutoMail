FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "pydantic>=2.5"
COPY DrPost/ .
ENV HOST=0.0.0.0 PORT=6767 DB_PATH=/data/automail.db ATTACHMENT_DIR=/data/attachments
VOLUME /data
EXPOSE 6767
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6767/health')"
CMD ["python", "AutoMailAPI.py"]
