FROM python:3.12-slim
WORKDIR /app
COPY common/ /app/common/
COPY agent-reasoning/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent-reasoning/src/ /app/src/
EXPOSE 8003
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]
