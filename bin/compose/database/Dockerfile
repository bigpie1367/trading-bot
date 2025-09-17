FROM timescale/timescaledb:2.14.2-pg16

COPY compose/database/schema.sql /initdb.d/schema.sql
COPY compose/database/start.sh /start.sh
RUN chmod +x /start.sh

ENTRYPOINT ["/start.sh"]
