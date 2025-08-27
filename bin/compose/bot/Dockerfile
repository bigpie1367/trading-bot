# Python base image
FROM python:3.11-slim

# Python 환경 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul

# 작업 디렉토리 설정
WORKDIR /app

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc tzdata && \
    rm -rf /var/lib/apt/lists/*

# requirements 설치
COPY bin/requirements/base.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

# 애플리케이션 소스 복사
COPY bot /app

# 기본 커맨드는 bash로, 각 컨테이너에서는 docker-compose에서 override
CMD ["bash"]
