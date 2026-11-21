FROM python:3.12-alpine
WORKDIR /app
COPY app.py market_data.py risk.py /app/
COPY static /app/static
ENV PYTHONUNBUFFERED=1 FLY_DB=/data/paper.db FLY_HOST=0.0.0.0
EXPOSE 8877
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8877/healthz',timeout=3).close()" || exit 1
CMD ["python", "app.py"]
