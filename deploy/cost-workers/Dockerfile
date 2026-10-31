FROM us-east1-docker.pkg.dev/seismik-15bbb/seismik/event-forwarder@sha256:36d4ac17dbabdade6d924f12bc6664725a7ee101371e5d06d9fda3b67471e97c AS forwarder
FROM us-east1-docker.pkg.dev/seismik-15bbb/seismik/seismik-dispatcher@sha256:e724f296e24b364cf9d7081f5ec266d1edd1f1cb5dc9ccedd8f321523340fc69
COPY --from=forwarder /app /opt/forwarder/app
COPY --from=forwarder /usr/local /opt/forwarder/runtime
COPY supervisor.py /app/worker_supervisor.py
RUN python -c "import dispatcher.combined" && PYTHONHOME=/opt/forwarder/runtime LD_LIBRARY_PATH=/opt/forwarder/runtime/lib PYTHONPATH=/opt/forwarder/app/src /opt/forwarder/runtime/bin/python3.12 -c "from dispatcher.pubsub_forwarder import _endpoint; assert _endpoint('https://example.org', 'magnitude_estimate_update').endswith('/magnitude-update')"
CMD ["python", "/app/worker_supervisor.py"]
