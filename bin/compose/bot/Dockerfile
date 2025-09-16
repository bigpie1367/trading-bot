# Python base image (GIL 비활성화 가능 빌드)
FROM dnalinux/pythonnogil:latest

# Python 환경 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul

# 작업 디렉토리 설정
WORKDIR /app

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        libpq-dev \
        tzdata \
        gcc \
        g++ \
        make && \
    rm -rf /var/lib/apt/lists/*

# requirements 설치
COPY bin/requirements/base.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

# 애플리케이션 소스 복사
COPY bot /app/bot

# 기본 커맨드
CMD ["python", "-m", "celery", "-A", "bot.tasks", "worker", "--loglevel=INFO"]
