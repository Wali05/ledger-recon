FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
ARG INSTALL_AI=false
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt && if [ "$INSTALL_AI" = "true" ]; then pip install --no-cache-dir -r requirements-ai.txt; fi
COPY . .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=5s --start-period=20s --retries=12 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/health', timeout=3)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
