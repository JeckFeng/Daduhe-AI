FROM python:3.11-slim
WORKDIR /app
COPY common/daduhe_common/ /app/daduhe_common/
COPY graph-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY graph-engine/src/ /app/src/
EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
