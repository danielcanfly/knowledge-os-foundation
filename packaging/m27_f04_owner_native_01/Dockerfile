# Real Owner-controlled Nonprod App; no secrets, Git checkout or vendor in image.
# Frozen C1 source modules and their SHA lock are copied from an exact-only context.
FROM python@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6
RUN apt-get update \
 && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/m27
COPY --chown=65532:65532 knowledge_engine/ /opt/m27/knowledge_engine/
COPY --chown=65532:65532 native_entrypoint.py native_runner.py native_https_provider.py source_lock.json /opt/m27/app/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/m27/knowledge_engine
LABEL org.opencontainers.image.title="M27 Owner Nonprod Native Product App"
LABEL org.opencontainers.image.revision="7aa58392bcf5f4be493912c8a2817d0e4d08df52"
LABEL org.opencontainers.image.description="Owner controlled source-locked native App; NOT formal F04 or Production"
USER 65532:65532
ENTRYPOINT ["python3.11","/opt/m27/app/native_entrypoint.py"]
