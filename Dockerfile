FROM python:3.12-alpine
RUN addgroup -S fly && adduser -S -u 10001 -G fly fly && mkdir -p /app /data && chown -R fly:fly /app /data
WORKDIR /app
COPY --chown=fly:fly app.py auth.py market_data.py risk.py performance.py historical.py market_cache.py analytics.py sectors.py portfolio_intelligence.py simulation.py market_simulation.py pdf_report.py /app/
COPY --chown=fly:fly static /app/static
ENV PYTHONUNBUFFERED=1 FLY_DB=/data/paper.db FLY_HOST=0.0.0.0
USER fly
EXPOSE 8877
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8877/healthz',timeout=3).close()" || exit 1
CMD ["python", "app.py"]
