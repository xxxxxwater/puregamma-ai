FROM python:3.12-slim-bookworm

WORKDIR /runtime
COPY services/nautilus-runtime/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --only-binary=nautilus_trader -r requirements.txt
COPY services/nautilus-runtime/app ./app
COPY services/nautilus-runtime/adapters ./adapters
COPY packages ./packages
RUN useradd --create-home --uid 10002 runtime \
    && mkdir -p /runtime/state \
    && chown -R runtime:runtime /runtime
USER runtime
ENV PYTHONPATH=/runtime
EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
