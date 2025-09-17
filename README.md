# Trading Bot

업비트(Upbit) 기반 코인 자동매매 봇.   

6가지 트레이딩 전략을 앙상블하여 매매 신호를 생성하고,  
Celery를 활용한 분산 처리로 실시간 데이터 수집과 자동매매를 수행.

## 주요 기능

### 구현 완료
- **실시간 데이터 수집**: 업비트 API를 통한 분봉 데이터 자동 수집 (매분)
- **앙상블 트레이딩 전략**: 6가지 전략을 가중치 기반으로 조합
- **자동매매 실행**: 매수/매도 신호에 따른 지정가 주문 실행
- **백테스팅 및 최적화**: 과거 3개월 데이터 기반 전략 파라미터 최적화 (매일)
- **분산 처리**: Celery를 활용한 워커 기반 아키텍처
- **데이터베이스**: TimescaleDB를 활용한 시계열 데이터 저장

### 개발 예정
- **포지션 관리**: 장기/단기 포지션 추적 및 관리
- **리스크 관리**: 손절매, 익절매 자동화
- **모니터링 대시보드**: 실시간 수익률 및 성과 모니터링
- **알림 시스템**: 매매 신호 및 오류 알림

## 트레이딩 전략

### 1. Trend Strategy
- 단순한 추세 추종 전략
- 이전 가격 대비 현재 가격 비교
- 신호: 상승 시 +1, 하락 시 -1

### 2. Momentum Strategy
- 5기간 모멘텀 기반 전략
- 과거 가격 대비 현재 가격 변화율 분석
- 신호: 양수 변화 시 +1, 음수 변화 시 -1

### 3. Swing Strategy
- 단기(5기간) vs 장기(20기간) 이동평균 비교
- 스윙 트레이딩 신호 생성
- 신호: 단기평균 > 장기평균 시 +1, 반대 시 -1

### 4. Scalping Strategy
- 0.1% 수준의 미세한 가격 변화 포착
- 초단타 스캘핑 전략
- 신호: 0.1% 이상 상승 시 +1, 0.1% 이상 하락 시 -1

### 5. Day Strategy
- 일중 가격 변화 기반 전략
- 단기 가격 움직임 분석
- 신호: 상승 시 +1, 하락 시 -1

### 6. Price Action Strategy
- 과거 최고가/최저가 돌파 기반 전략
- 가격 액션 패턴 분석
- 신호: 최고가 돌파 시 +1, 최저가 하락 시 -1

### 앙상블 신호 생성
- 각 전략의 가중합으로 최종 신호 생성
- 임계값(threshold) 이상일 때 매수, 이하일 때 매도
- 가중치는 최적화를 통해 동적 조정

## 아키텍처
![이미지](https://github.com/user-attachments/assets/d9d79f15-c4b2-45c5-991c-65120b861d83)

## 기술 스택

### Backend
- **Python**: 3.13 (no-gil)
- **Framework**: Celery
- **API Client**: Upbit API
- **Data Processing**: NumPy, Pandas

### Database & Storage
- **TimescaleDB**: 시계열 데이터 저장 (PostgreSQL 기반)
- **Redis**: 메시지 브로커 및 캐시

### Infrastructure
- **Container**: Docker & Docker Compose
- **Logging**: JSON 구조화 로깅
- **Scheduling**: Celery Beat

## 프로젝트 구조

```
trading-bot/
├── bot/                          # 메인 애플리케이션
│   ├── __init__.py               
│   ├── collector.py              # 데이터 수집 모듈
│   ├── trader.py                 # 자동매매 실행 모듈
│   ├── optimizer.py              # 전략 최적화 모듈
│   ├── strategies.py             # 트레이딩 전략 정의
│   ├── upbit.py                  # 업비트 API 클라이언트
│   ├── storage.py                # 데이터베이스 모듈
│   ├── scheduler.py              # Celery 스케줄러 설정
│   ├── tasks.py                  # Celery 태스크 정의
│   └── utils.py                  # 유틸리티 함수
├── bin/                          # 배포 및 설정
│   ├── docker-compose.yml        # Docker Compose 설정
│   ├── restart_docker.sh         # Docker 재시작 스크립트
│   ├── compose/
│   │   ├── bot/Dockerfile        # 봇 컨테이너 이미지
│   │   └── database/
│   │       ├── Dockerfile        # DB 컨테이너 이미지
│   │       ├── schema.sql        # 데이터베이스 스키마
│   │       └── start.sh          # DB 초기화 스크립트
│   ├── requirements/
│   │   └── base.txt              # Python 의존성
│   └── .envs/                    # 환경 변수 설정
│       ├── .bot                  # 봇 설정 (API 키 포함)
│       └── .database             # DB 설정
└── README.md                     # 프로젝트 문서
```

### 주요 모듈 설명

#### `bot/collector.py`
- 업비트 API에서 분봉 데이터 수집
- TimescaleDB에 데이터 저장 (UPSERT 방식)
- 중복 데이터 방지 및 효율적 저장

#### `bot/trader.py`
- 6가지 전략의 앙상블 신호 생성
- 지정가 매수/매도 주문 실행
- 수수료 및 최소 주문 금액 고려
- 주문 및 체결 내역 DB 저장

#### `bot/optimizer.py`
- 3개월 과거 데이터 기반 백테스팅
- 그리드 서치를 통한 가중치/임계값 최적화
- 멀티스레드 병렬 처리
- Sharpe 비율 기반 최적 파라미터 선택

#### `bot/strategies.py`
- 6가지 트레이딩 전략 구현
- 각 전략별 신호 생성 로직
- 앙상블 신호 조합

#### `bot/upbit.py`
- 업비트 API 클라이언트
- JWT 인증 처리
- 호가단위 맞춤 가격 반올림
- 주문 및 계좌 조회 기능

## 시작하기

### 1. 환경 설정

```bash
# 프로젝트 클론
git clone <repository-url>
cd trading-bot

# 환경 변수 설정
cp bin/.envs/.bot.example bin/.envs/.bot
cp bin/.envs/.database.example bin/.envs/.database
```

### 2. 환경 변수 수정

**bin/.envs/.bot**:
```env
# 데이터베이스 연결
DATABASE_URL=postgresql://trader:trader@database:5432/trading

# Celery 설정
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_BACKEND_URL=redis://redis:6379/1

# 업비트 API 키 (실제 키로 변경 필요)
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key

# 트레이딩 설정
MARKET=KRW-BTC
THRESHOLD=0.2
AGGRESSIVENESS=0.0015
FEE_RATE=0.0005
FEE_BUFFER=0.0005

# 최적화 설정
OPT_INITIAL_CASH=1000000
OPT_WINDOW=200
OPT_THREADS=4
OPT_THRESHOLDS=0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5

# 로깅 설정
LOG_LEVEL=INFO
```

**bin/.envs/.database**:
```env
POSTGRES_HOST=postgres
POSTGRES_DB=trading
POSTGRES_USER=trader
POSTGRES_PASSWORD=trader
```

### 3. Docker Compose로 실행

```bash
cd bin
sh restart_docker.sh
```

### 4. 서비스 확인

```bash
# 로그 확인
docker-compose logs -f

# 서비스 상태 확인
docker-compose ps
```

## 데이터베이스 스키마

### 주요 테이블

#### `candles`
- 분봉 데이터 저장 (OHLCV)
- 시계열 최적화된 저장 구조
- 중복 데이터 방지를 위한 UPSERT

#### `orders`
- 주문 정보 저장
- 매수/매도 주문 상태 추적
- 업비트 주문 ID 매핑

#### `trades`
- 체결 정보 저장
- 수수료 및 슬리피지 정보
- 주문별 체결 내역 추적

#### `optimizer_results`
- 전략 최적화 결과 저장
- 최적 파라미터 및 성과 지표
- 베스트 모델 마킹

#### `positions` (미사용)
- 포지션 관리 (현재 미구현)
- 장기/단기 포지션 추적

#### `equity_curve` (미사용)
- 자산 곡선 추적 (현재 미구현)
- 실시간 수익률 모니터링

## 설정 옵션

### 트레이딩 파라미터

- `MARKET`: 거래할 코인 (기본값: KRW-BTC)
- `THRESHOLD`: 매매 신호 임계값 (기본값: 0.2)
- `AGGRESSIVENESS`: 주문 가격 공격성 (기본값: 0.0015)
- `FEE_RATE`: 거래 수수료율 (기본값: 0.0005)
- `FEE_BUFFER`: 수수료 버퍼 (기본값: 0.0005)

### 최적화 파라미터

- `OPT_INITIAL_CASH`: 백테스팅 초기 자금 (기본값: 1,000,000)
- `OPT_WINDOW`: 백테스팅 윈도우 크기 (기본값: 200)
- `OPT_THREADS`: 최적화 스레드 수 (기본값: 4)
- `OPT_THRESHOLDS`: 최적화할 임계값 목록 (쉼표 구분)

### 데이터 수집 설정

- `UNIT`: 분봉 단위 (기본값: 1분)
- `LOG_LEVEL`: 로그 레벨 (기본값: INFO)

### 데이터베이스 설정

- `DATABASE_URL`: PostgreSQL 연결 URL
- `CELERY_BROKER_URL`: Redis 브로커 URL
- `CELERY_BACKEND_URL`: Redis 백엔드 URL

## 워크플로우

### 실시간 트레이딩 (매분)
1. **데이터 수집**: 업비트에서 최신 분봉 데이터 수집
2. **전략 실행**: 6가지 전략으로 매매 신호 생성
3. **자동매매**: 신호에 따른 매수/매도 주문 실행
4. **주문 관리**: 주문 및 체결 내역 데이터베이스 저장

### 전략 최적화 (매일 01:00)
1. **데이터 로드**: 과거 3개월 분봉 데이터 조회
2. **백테스팅**: 다양한 파라미터 조합으로 성과 테스트
3. **최적화**: Sharpe 비율 기반 최적 파라미터 선택
4. **모델 업데이트**: 새로운 가중치 및 임계값 적용

### 스케줄링
- **Celery Beat**: 정확한 시간 간격으로 태스크 스케줄링
- **워커 분리**: 데이터 수집, 트레이딩, 최적화 워커 분리
- **큐 관리**: Redis 기반 태스크 큐 관리

## 주의사항
- **API 키 보안**: 환경변수에 저장, 코드에 하드코딩 금지
- **테스트 환경**: 실제 거래 전 충분한 백테스팅 및 페이퍼 트레이딩 권장

## 모니터링

### 로그 확인
```bash
# 전체 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f collector
docker-compose logs -f trader
docker-compose logs -f optimizer
docker-compose logs -f beat

# 실시간 로그 필터링
docker-compose logs -f | grep "trade executed"
docker-compose logs -f | grep "optimization done"
```

### 성과 지표 확인
- **총 수익률**: `total_return` (optimizer_results 테이블)
- **최대 낙폭**: `max_drawdown` (optimizer_results 테이블)
- **샤프 비율**: `sharpe` (optimizer_results 테이블)
- **승률**: `win_rate` (optimizer_results 테이블)

## 향후 개발 계획

### Phase 1: 포지션 관리 시스템
- 장기/단기 포지션 추적 및 관리
- 포지션별 수익률 계산
- 포지션 크기 조절 로직

### Phase 2: 리스크 관리
- 손절매/익절매 자동화
- 최대 손실 한도 설정
- 변동성 기반 포지션 크기 조절

### Phase 3: 모니터링 대시보드
- 실시간 수익률 및 성과 모니터링
- 웹 기반 대시보드 구축
- 알림 시스템 (Slack, Discord 등)

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.