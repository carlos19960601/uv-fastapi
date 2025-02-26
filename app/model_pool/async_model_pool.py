# 异步模型池 | Async model pool
import asyncio
import threading
from asyncio import Queue
from typing import Optional

from app.utils.logging_utils import configure_logging


class AsyncModelPool:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(AsyncModelPool, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        # 引擎名称 | Engine name
        engine: str,
        # openai_whisper 引擎设置 | openai_whisper Engine Settings
        openai_whisper_model_name: str,
        openai_whisper_device: str,
        openai_whisper_download_root: Optional[str],
        openai_whisper_in_memory: bool,
        # faster_whisper 引擎设置 | faster_whisper Engine Settings
        faster_whisper_model_size_or_path: str,
        faster_whisper_device: str,
        faster_whisper_device_index: int,
        faster_whisper_compute_type: str,
        faster_whisper_cpu_threads: int,
        faster_whisper_num_workers: int,
        faster_whisper_download_root: Optional[str],
        # 模型池设置 | Model Pool Settings
        min_size: int = 1,
        max_size: int = 1,
        max_instances_per_gpu: int = 1,
        init_with_max_pool_size: bool = True,
    ):
        """
        异步模型池，用于管理多个异步模型实例，并且会根据当前系统的 GPU 数量和 CPU 性能自动纠正错误的初始化参数，这个类是线程安全的。

        Asynchronous model pool, used to manage multiple asynchronous model instances, and will automatically correct based on the number of GPUs and CPU performance of the current system, the incorrectly initialized parameters. This class is thread-safe.

        Args:
            engine (str): 引擎名称，目前支持 "openai_whisper", "faster_whisper" | Engine name, currently supports "openai_whisper", "faster_whisper"
            openai_whisper_model_name (str): 模型名称，如 "base", "small", "medium", "large" | Model name, e.g., "base", "small", "medium", "large"
            openai_whisper_device (str): 设备名称，如 "cpu" 或 "cuda"，为 None 时自动选择 | Device name, e.g., "cpu" or "cuda"
            openai_whisper_download_root (str | None): 模型下载根目录 | Model download root directory
            openai_whisper_in_memory (bool):是否在内存中加载模型 | Whether to load the model in memory

            faster_whisper_model_size_or_path (str): 模型名称或路径 | Model name or path
            faster_whisper_device (str): 设备名称，如 "cpu" 或 "cuda"，为 None 时自动选择 | Device name, e.g., "cpu" or "cuda"
            faster_whisper_device_index (int): 设备ID，当 faster_whisper_device 为 "cuda" 时有效 | Device ID, valid when faster_whisper_device is "cuda"
            faster_whisper_compute_type (str): 模型推理计算类型 | Model inference calculation type
            faster_whisper_cpu_threads (int): 模型使用的CPU线程数，设置为 0 时使用所有可用的CPU线程 | The number of CPU threads used by the model, set to 0 to use all available CPU threads
            faster_whisper_num_workers (int): 模型worker数 | Model worker count
            faster_whisper_download_root (str | None): 模型下载根目录 | Model download root directory

            min_size (int, optional): 模型池的最小大小 | Minimum pool size
            max_size (int, optional): 模型池的最大大小 | Maximum pool size
            max_instances_per_gpu (int, optional): 每个 GPU 最多支持的实例数量 | The maximum number of instances supported by each GPU
            init_with_max_pool_size (bool, optional): 是否在模型池初始化时以最大并发任务数创建模型实例 |
                                                  Whether to create model instances with the maximum number of concurrent tasks
                                                  when the model pool is initialized
        """
        # 防止重复初始化 | Prevent re-initialization
        if getattr(self, "_initialized", False):
            return

        if min_size > max_size:
            raise ValueError("min_size cannot be greater than max_size.")

        self.logger = configure_logging(name=__name__)

        # 模型引擎 | Model engine
        self.engine = engine

        # openai_whisper 引擎设置 | openai_whisper Engine Settings
        self.openai_whisper_model_name = openai_whisper_model_name
        self.openai_whisper_device = openai_whisper_device
        self.openai_whisper_download_root = openai_whisper_download_root
        self.openai_whisper_in_memory = openai_whisper_in_memory

        # faster_whisper 引擎设置 | faster_whisper Engine Settings
        self.fast_whisper_model_size_or_path = faster_whisper_model_size_or_path
        self.fast_whisper_device = faster_whisper_device
        self.faster_whisper_device_index = faster_whisper_device_index
        self.fast_whisper_compute_type = faster_whisper_compute_type
        self.fast_whisper_cpu_threads = faster_whisper_cpu_threads
        self.fast_whisper_num_workers = faster_whisper_num_workers
        self.fast_whisper_download_root = faster_whisper_download_root

        self.min_size = min_size
        self.max_size = self.get_optimal_max_size(max_size)
        self.pool = Queue(maxsize=self.max_size)
        self.init_with_max_pool_size = init_with_max_pool_size
        self.loading_lock = asyncio.Lock()

    async def initialize_pool(self) -> None:
        """
        异步初始化模型池，按批次加载模型实例以减少并发冲突。

        Initialize the model pool asynchronously by loading the minimum number of model instances in batches
        to reduce concurrent download conflicts.
        """
        instances_to_create = (
            self.max_size if self.init_with_max_pool_size else self.min_size
        )
        # 每批加载的实例数，用于减少并发冲突 | Number of instances to load per batch to reduce concurrent conflicts
        batch_size = 1

        self.logger.info(
            f"""
        Initializing AsyncModelPool with total {instances_to_create} instances...
        Engine           : {self.engine}
        Min pool size    : {self.min_size}
        Max pool size    : {self.max_size}
        Max instances/GPU: {self.max_instances_per_gpu}
        Init with max size: {self.init_with_max_pool_size}
        This may take some time, please wait...
        """
        )

        try:
            async with self.loading_lock:
                if self.current_size >= self.min_size:
                    self.logger.info(
                        "AsyncModelPool is already initialized. Skipping initialization..."
                    )
                    return

                # 分批加载模型实例 | Load model instances in batches
                for i in range(0, instances_to_create, batch_size):
                    tasks = [
                        self._create_and_put_model(i + j)
                        for j in range(batch_size)
                        if i + j < instances_to_create
                    ]
                    await asyncio.gather(*tasks)
                    self.logger.info(
                        f"Batch of {batch_size} model instance(s) created."
                    )

                self.logger.info(
                    f"Successfully initialized AsyncModelPool with {instances_to_create} instances."
                )
        except Exception as e:
            self.logger.error(f"Failed to initialize AsyncModelPool: {e}")

    def get_optimal_max_size(self, max_size: int) -> int:
        """
        根据当前系统的 GPU 数量、CPU 性能和用户设置的最大池大小，返回最优的 max_size。

        Return the optimal max_size based on the number of GPUs, CPU performance, and
        the maximum pool size set by the user.

        :param max_size: 用户设置的最大池大小 | Maximum pool size set by the user
        :return: 最优的 max_size | Optimal max_size
        """
        # 检查用户输入是否为有效的正整数 | Validate user input
        if max_size < 1:
            self.logger.warning("Invalid max_size provided. Setting max_size to 1.")
            max_size = 1

        optimal_size = max_size

        return optimal_size

    async def get_model(
        self, timeout: Optional[float] = 5.0, strategy: str = "existing"
    ):
        """
        异步获取模型实例。如果池为空且未达到最大大小，则按指定策略创建新的模型实例。

        Asynchronously retrieve a model instance. If the pool is empty and the maximum pool size
        has not been reached, a new model instance will be created based on the specified strategy.

        :param timeout: 超时时间（以秒为单位），用于等待从池中获取模型实例。默认为 5 秒。
                        Timeout in seconds for waiting to retrieve a model instance from the pool.
                        Defaults to 5 seconds.
        :param strategy: 获取模型的策略 ("existing", "dynamic")。默认为 "existing"。
                            Strategy for retrieving a model instance ("existing", "dynamic"). Defaults to "existing".

        :return: 模型实例 | Model instance

        :raises RuntimeError: 当模型池已达到最大大小，且所有实例都正在使用时。
                                Raises RuntimeError when the model pool is exhausted and all instances are in use.
        """
        self.logger.info(
            f"Attempting to retrieve a model instance from the pool with strategy '{strategy}'..."
        )

        try:
            if strategy == "existing":
                # 尝试从池中获取现有模型实例 | Attempt to retrieve an existing model instance
                try:
                    model = await asyncio.wait_for(self.pool.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    self.logger.error(
                        "All model instances are in use, and the pool is exhausted."
                    )
                    raise RuntimeError(
                        "Model pool exhausted, and all instances are currently in use."
                    )

            elif strategy == "dynamic":
                # 在池大小允许的情况下动态创建新模型 | Dynamically create a new model if pool size allows
                model = await asyncio.wait_for(self.pool.get(), timeout=timeout)

            else:
                # 默认尝试从池中获取模型实例 | Default: attempt to retrieve from pool
                model = await asyncio.wait_for(self.pool.get(), timeout=timeout)

        except Exception as e:
            self.logger.error(f"Failed to retrieve a model instance from the pool: {e}")
            raise RuntimeError(
                "Unexpected error occurred while retrieving a model instance."
            )
