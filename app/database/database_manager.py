import asyncio
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.utils.logging_utils import configure_logging

from .models import task_models

# 配置日志记录器 | Configure logger
logger = configure_logging(name=__name__)


class DatabaseManager:
    def __init__(
        self,
        database_type: str,
        database_url: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        reconnect_interval: int = 5,
    ) -> None:
        """
        初始化数据库管理器并根据数据库类型动态绑定相应的数据库引擎和会话。

        Initializes the database manager with dynamic binding based on database type.

        :param database_type: 数据库类型 ("sqlite" 或 "mysql") | Database type ("sqlite" or "mysql")
        :param database_url: 数据库 URL | Database URL
        :param loop: 异步事件循环（可选）| Event loop (optional)
        :param reconnect_interval: 重连间隔（秒）| Reconnect interval (seconds)
        """
        self.database_type: str = database_type
        self.database_url: str = database_url
        self._is_connected: bool = False
        self._engine: Optional[Engine] = None

    def initialize(self) -> None:
        """
        初始化数据库引擎和会话工厂，并根据数据库类型配置引擎。自动创建缺失的表。

        Initialize the database engine and session factory, configure engine based on database type,
        and automatically create any missing tables.
        """
        self._connect()

    def _connect(self) -> None:
        while not self._is_connected:
            try:
                if self.database_type == "mysql":
                    self._engine = create_engine(self.database_url, echo=True)
                elif self.database_type == "sqlite":
                    self._engine = create_engine(self.database_url, echo=True)

                SQLModel.metadata.create_all(self._engine)

                self._is_connected = True
                logger.info(
                    f"{self.database_type.upper()} database connected and tables initialized successfully."
                )
            except Exception:
                raise

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        获取数据库会话生成器

        Get a database session generator.

        :return: 数据库会话 | Database session
        """
        if not self._is_connected:
            self._connect()

        with Session(self._engine) as session:
            yield session
