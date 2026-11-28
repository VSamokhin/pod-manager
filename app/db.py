import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from . import config


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Image(Base):
    __tablename__ = "images"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    kind: Mapped[str] = mapped_column(String(16), default="other")  # raster | vector | other
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    has_preview: Mapped[bool] = mapped_column(Boolean, default=False)
    interesting: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown | successful | unsuccessful
    tags: Mapped[str] = mapped_column(String(500), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    uploaded_by: Mapped[User | None] = relationship()
    parent: Mapped[Image | None] = relationship(remote_side="Image.id", back_populates="derived")
    derived: Mapped[list[Image]] = relationship(back_populates="parent")
    template: Mapped[Template | None] = relationship()
    drop_links: Mapped[list[DropImage]] = relationship(back_populates="image", cascade="all, delete-orphan")

    @property
    def display_title(self) -> str:
        return self.title or self.original_filename

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class DropState(Base):
    __tablename__ = "drop_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    color: Mapped[str] = mapped_column(String(16), default="#888888")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class GoodsType(Base):
    __tablename__ = "goods_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    print_width_mm: Mapped[float | None] = mapped_column(nullable=True)
    print_height_mm: Mapped[float | None] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Drop(Base):
    __tablename__ = "drops"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    state_id: Mapped[int | None] = mapped_column(ForeignKey("drop_states.id", ondelete="SET NULL"), nullable=True)
    planned_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD, optional
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    state: Mapped[DropState | None] = relationship()
    items: Mapped[list[DropImage]] = relationship(
        back_populates="drop", cascade="all, delete-orphan", order_by="DropImage.position"
    )


drop_image_goods = Table(
    "drop_image_goods",
    Base.metadata,
    Column("drop_image_id", ForeignKey("drop_images.id", ondelete="CASCADE"), primary_key=True),
    Column("goods_type_id", ForeignKey("goods_types.id", ondelete="CASCADE"), primary_key=True),
)


class DropImage(Base):
    __tablename__ = "drop_images"
    __table_args__ = (UniqueConstraint("drop_id", "image_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    drop_id: Mapped[int] = mapped_column(ForeignKey("drops.id", ondelete="CASCADE"))
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")

    drop: Mapped[Drop] = relationship(back_populates="items")
    image: Mapped[Image] = relationship(back_populates="drop_links")
    goods: Mapped[list[GoodsType]] = relationship(secondary=drop_image_goods)


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def params(self) -> dict:
        try:
            return json.loads(self.params_json or "{}")
        except ValueError:
            return {}


engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> Engine:
    global engine, SessionLocal  # noqa: PLW0603 - module-level engine, configured once at startup
    config.ensure_dirs()
    engine = create_engine(url or f"sqlite:///{config.DB_PATH}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn: Any, _record: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return engine


def session_factory() -> sessionmaker[Session]:
    if SessionLocal is None:
        raise RuntimeError("init_engine() has not been called")
    return SessionLocal


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()
