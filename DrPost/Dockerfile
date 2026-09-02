FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 6767

CMD ["uvicorn", "AutoMailAPI:app", "--host", "0.0.0.0", "--port", "6767"]