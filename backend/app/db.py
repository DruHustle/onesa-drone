from contextlib import contextmanager
from threading import RLock
import hashlib
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import sessionmaker
from .models import Base, Tenant, SchemaRevision


class Store:
    def __init__(self, url):
        self.lock = RLock()
        opts = {"pool_pre_ping": True}
        if url.startswith("sqlite:"):
            opts["connect_args"] = {"check_same_thread": False, "timeout": 5}
        else:
            opts.update(pool_size=3, max_overflow=2, pool_timeout=5, connect_args={"connect_timeout": 5})
        self.engine = create_engine(url, **opts)
        if url.startswith("sqlite:"):

            @event.listens_for(self.engine, "connect")
            def pragma(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA journal_mode=WAL")

        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def checksum(self):
        ddl = "\n".join(
            str(CreateTable(table).compile(dialect=self.engine.dialect))
            for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name)
        )
        return hashlib.sha256(ddl.encode()).hexdigest()

    def initialize(self):
        """Explicit initial migration; never silently accepts a changed source schema."""
        with self.lock, self.engine.begin() as conn:
            if self.engine.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(92841031)"))
            Base.metadata.create_all(conn)
            expected = self.checksum()
            row = conn.execute(
                select(SchemaRevision.checksum).where(SchemaRevision.version == "0001")
            ).scalar_one_or_none()
            if row is None:
                conn.execute(SchemaRevision.__table__.insert().values(version="0001", checksum=expected))
            elif row != expected:
                raise RuntimeError(
                    "Schema source differs from applied migration; explicit migration required"
                )

    def verify(self):
        with self.session() as db:
            row = db.get(SchemaRevision, "0001")
            if not row or row.checksum != self.checksum():
                raise RuntimeError("Operational schema migration is missing or incompatible")

    @contextmanager
    def transaction(self, tenant_id=None):
        with self.lock, self.session.begin() as db:
            if tenant_id:
                db.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
            yield db
