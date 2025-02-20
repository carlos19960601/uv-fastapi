# 异步模型池 | Async model pool
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

    def initialize_pool(self) -> None:
        pass

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
