FROM docker.m.daocloud.io/library/python:3.10-slim-bookworm@sha256:2559be987fd64d61badbdafd303ea58a9ccab36d6c3c08bce219e762177d2eca
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg \
    PYTHONPATH=/app:/app/sack:/app/sack/Agents:/app/sack/Tools:/app/sack/knowledge
RUN sed -i 's#http://deb.debian.org#https://mirrors.aliyun.com#g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends libgomp1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 sackeda && useradd -m -u 10001 -g 10001 sackeda
COPY sack/knowledge/deployment/eda/requirements.txt /tmp/eda-requirements.txt
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/eda-requirements.txt && pip check
COPY . /app
WORKDIR /app/sack
USER 10001:10001
ENTRYPOINT ["python", "/app/sack/knowledge/deployment/eda/run_eda.py"]
CMD ["--check"]
