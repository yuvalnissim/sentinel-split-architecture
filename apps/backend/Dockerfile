FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --chown=10001:10001 server.py /app/server.py

USER 10001:10001

EXPOSE 8080

CMD ["python", "/app/server.py"]