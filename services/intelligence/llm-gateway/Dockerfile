FROM python:3.11-slim
WORKDIR /app
COPY common/daduhe_common/ /app/daduhe_common/
COPY llm-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY llm-gateway/src/ /app/src/
EXPOSE 8004
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004"]
