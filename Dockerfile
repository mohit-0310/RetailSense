FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV RETAILSENSE_PREPARED_DIR=prepared
ENV RETAILSENSE_USE_OPENAI_AGENTS=1
ENV RETAILSENSE_AGENT_TIMEOUT_SECONDS=12

EXPOSE 7860

CMD ["uvicorn", "retailsense.api:app", "--host", "0.0.0.0", "--port", "7860"]
