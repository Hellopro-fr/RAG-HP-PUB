import logging
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from application.clock import utcnow
from application.types_service import TypeService
from application.unit_service import UnitService
from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import Base
from infrastructure.grpc.server import build_server
from infrastructure.http_server import db_ping, start_http_server
from infrastructure.messaging.publisher import PikaPublisher
from infrastructure.messaging.relay import OutboxRelay

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def main() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory.begin() as session:
        bootstrap(session, utcnow())

    stop = threading.Event()
    relay = OutboxRelay(session_factory, PikaPublisher(settings.RABBITMQ_URL, settings.UNITS_EXCHANGE))
    threading.Thread(target=relay.run_forever, args=(stop, settings.RELAY_POLL_SECONDS),
                     daemon=True, name="outbox-relay").start()
    start_http_server(settings.HTTP_PORT, lambda: db_ping(engine))

    server, port = build_server(UnitService(session_factory), TypeService(session_factory),
                                admin_key=settings.UNITS_ADMIN_KEY, port=settings.GRPC_PORT,
                                max_workers=settings.GRPC_MAX_WORKERS)
    server.start()
    logging.info("unit-registry-service: gRPC on %d, HTTP on %d", port, settings.HTTP_PORT)
    try:
        server.wait_for_termination()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
