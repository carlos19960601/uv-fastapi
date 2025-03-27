# 异步模型池 | Async model pool
import asyncio
import datetime
import gc
import threading
from asyncio import Queue
from typing import Optional

from sympy import EX
import torch

# OpenAI Whisper 模型 | OpenAI Whisper model
import whisper

# Faster-Whisper 模型 | Faster-Whisper model
from faster_whisper import WhisperModel

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

        # 检查是否有多个可用的 GPU | Check if multiple GPUs are available
        self.num_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 0

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
        self.max_instances_per_gpu = max_instances_per_gpu
        self.init_with_max_pool_size = init_with_max_pool_size
        self.pool = Queue(maxsize=self.max_size)
        self.current_size = 0
        self.size_lock = asyncio.Lock()
        self.resize_lock = asyncio.Lock()
        self.loading_lock = asyncio.Lock()

        self._initialized = True

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

        # 检测可用的 GPU 数量 | Check the number of available GPUs
        num_gpus = torch.cuda.device_count()
        # 获取 CPU 线程数 | Get the number of CPU threads
        num_cpu_threads = torch.get_num_threads()

        if num_gpus == 0:
            # CPU-only 系统 | CPU-only system
            optimal_size = (
                1 if num_cpu_threads <= 4 else min(max_size, num_cpu_threads // 2)
            )
            self.logger.info(
                f"No GPU available. Setting max_size to {optimal_size} for CPU-only system."
            )
        elif num_gpus == 1:
            # 单 GPU 系统 | Single GPU system
            optimal_size = 1
            self.logger.info(
                "Single GPU detected. Limiting max_size to 1 to avoid GPU resource contention."
            )
        else:
            # 多 GPU 系统 | Multi-GPU system
            max_possible_instances = num_gpus * self.max_instances_per_gpu
            optimal_size = min(max_size, max_possible_instances)
            self.logger.info(
                f"Multiple GPUs detected ({num_gpus}). Setting max_size to {optimal_size}, "
                f"based on max {self.max_instances_per_gpu} instances per GPU."
            )

        self.logger.info(
            f"Optimized Model Pool `max_size` attribute from user input: {max_size} -> {optimal_size}"
        )

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
                    self.logger.info(
                        "Model instance successfully retrieved from the pool (existing instance)."
                    )
                    return model
                except asyncio.TimeoutError:
                    # 如果池为空且等待超时，则检查是否允许创建新实例 | Check if new instances can be created on timeout
                    async with self.size_lock:
                        if self.current_size < self.max_size:
                            instance_index = self.current_size
                            await self._create_and_put_model(instance_index)
                            self.logger.info(
                                f"Pool exhausted. Created new model instance with index {instance_index}."
                            )
                            # 获取刚创建的模型 | Retrieve the newly created model
                            model = await self.pool.get()
                            return model
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
                self.logger.info("Model instance successfully retrieved from the pool.")
                return model

        except Exception as e:
            self.logger.error(f"Failed to retrieve a model instance from the pool: {e}")
            raise RuntimeError(
                "Unexpected error occurred while retrieving a model instance."
            )

    async def return_model(self, model) -> None:
        """
        将模型实例归还到池中。

        Return a model instance to the pool.

        :param model: 要归还的模型实例 | The model instance to return
        """
        try:
            # 检查池是否已满 | Check if the pool is already full
            if self.pool.full():
                self.logger.warning(f"""
                Model pool is full. Unable to return model instance.
                Model will be destroyed to prevent resource leak.
                """)
                await self._destroy_model(model)
                return

            # 尝试将模型放入池中 | Try to return the model to the pool
            await self.pool.put(model)
            self.logger.info(f"""
            Model instance successfully returned to the pool.
            Current pool size (after return): {self.pool.qsize()}
            """)
        except (RuntimeError, AttributeError) as e:
            # 捕获模型实例无效的情况 | Catch cases where the model instance is invalid
            self.logger.error(f"Failed to return model to pool due to invalid model instance: {str(e)}", exc_info=True)
            await self._destroy_model(model)
                 
        except Exception as e:
            # 捕获任何其他未预料到的异常 | Capture any other unexpected exceptions
            self.logger.error(f"An unexpected error occurred while returning model to pool: {str(e)}", exc_info=True)
            await self._destroy_model(model)

    def allocate_device(
        self, instance_index: int, device_type: Optional[str], model_type: str
    ) -> dict:
        """
        根据实例索引、设备类型和模型类型为模型实例分配设备

        Allocate a device for the model instance based on instance index, device type, and model type.

        :param instance_index: 当前模型实例的索引 | Index of the current model instance
        :param device_type: 设备类型（"cpu", "cuda", "auto", 或 None） | Type of device ("cpu", "cuda", "auto", or None)
        :param model_type: 模型类型（"faster_whisper" 或 "openai_whisper"） | Model type ("faster_whisper" or "openai_whisper")
        :return: 包含设备信息的字典，适配不同的模型初始化参数 | Dictionary containing device information for different model initialization
        """
        if model_type == "faster_whisper" and device_type == "auto":
            device_type = "cuda" if torch.cuda.is_available() else "cpu"
        elif model_type == "openai_whisper" and device_type is None:
            device_type = "cuda" if torch.cuda.is_available() else "cpu"

        # 默认设备分配 | Default device allocation
        allocation = {"device": "N/A", "compute_type": "N/A"}

        if device_type == "cuda" and self.num_gpus > 0:
            if self.num_gpus == 1:
                # 单 GPU 情况，分配到 GPU 0 并使用 float16 | Single GPU case, assign to GPU 0 with float16
                allocation["device"] = "cuda"
            else:
                # 多 GPU 情况下考虑 max_instances_per_gpu 限制 | Consider max_instances_per_gpu in multi-GPU setup
                allocation["device"] = "cuda"
        else:
            # 无 GPU 情况，分配到 CPU 并使用 float32 | No GPU case, assign to CPU with float32
            allocation["device"] = "cpu"
            allocation["compute_type"] = (
                "float32" if model_type == "faster_whisper" else "N/A"
            )

        # 构建日志信息，包含系统上下文信息 | Build log information, including system context
        gpu_message = (
            "(Single GPU system detected, assigned to GPU 0)"
            if self.num_gpus == 1
            else (
                "(Multi-GPU system detected, assigned using max_instances_per_gpu limit)"
                if self.num_gpus > 1
                else (
                    "(No GPU available, falling back to CPU)"
                    if allocation["device"] == "cpu"
                    else "(No GPU available or CPU explicitly specified)"
                )
            )
        )

        # 输出日志信息 | Log the allocation details
        self.logger.info(
            f"""
        Allocating device for model instance {instance_index}:
        Instance index      : {instance_index}
        Model type          : {model_type}
        Device type         : {device_type}
        Total GPUs          : {self.num_gpus}
        Total CPU Threads   : {torch.get_num_threads()}
        Max Instances       : {self.max_size}
        Max Instances/GPU   : {self.max_instances_per_gpu}
        Selected device     : {allocation["device"]}
        Compute type        : {allocation["compute_type"]}
        Device index        : {allocation.get("device_index", "N/A")}
        {gpu_message}
        """
        )

        return allocation

    async def _create_and_put_model(self, instance_index: int) -> None:
        """
        异步创建新的模型实例并放入池中。

        Asynchronously create a new model instance and put it into the pool.
        """
        try:
            # 使用 allocate_device 分配设备和配置 | Use allocate_device to assign device and configuration
            device_type = (
                self.fast_whisper_device
                if self.engine == "faster_whisper"
                else self.openai_whisper_device
            )
            device_allocation = self.allocate_device(
                instance_index, device_type, self.engine
            )

            # 输出配置信息日志 | Log configuration information
            self.logger.info(
                f"""
                    Attempting to create a new model instance with the following configuration:
                    Engine           : {self.engine}
                    Model name       : {self.fast_whisper_model_size_or_path if self.engine == 'faster_whisper' else self.openai_whisper_model_name}
                    Device           : {device_allocation['device']}
                    Compute type     : {device_allocation['compute_type']}
                    Device index     : {device_allocation.get('device_index', 'N/A')}
                    Instance index   : {instance_index}
                    Current pool size: {self.current_size}
                    """
            )

            # 根据模型引擎类型创建实例 | Create model instance based on engine type
            if self.engine == "faster_whisper":
                start_time = datetime.datetime.now()
                # 在新线程中运行
                model = await asyncio.to_thread(
                    WhisperModel,
                    self.fast_whisper_model_size_or_path,
                    device=device_allocation["device"],
                    device_index=device_allocation.get("device_index", 0),
                    compute_type=device_allocation["compute_type"],
                    cpu_threads=self.fast_whisper_cpu_threads,
                    num_workers=self.fast_whisper_num_workers,
                    download_root=self.fast_whisper_download_root,
                )
                end_time = datetime.datetime.now()
            elif self.engine == "openai_whisper":
                start_time = datetime.datetime.now()
                model = await asyncio.to_thread(
                    whisper.load_model,
                    self.openai_whisper_model_name,
                    device=device_allocation["device"],
                    download_root=self.openai_whisper_download_root,
                    in_memory=self.openai_whisper_in_memory,
                )
                end_time = datetime.datetime.now()
            else:
                raise ValueError(
                    "Invalid engine specified. Choose 'openai_whisper' or 'faster_whisper'."
                )

            # 将模型放入池中 | Put model into the pool
            await self.pool.put(model)

            # 更新池大小 | Update pool size
            async with self.size_lock:
                self.current_size += 1

            # 计算加载时间（以秒为单位） | Calculate load time in seconds
            time_taken = (end_time - start_time).total_seconds()

            self.logger.info(
                f"""
                Successfully created and added a new model instance to the pool.
                Engine           : {self.engine}
                Device           : {device_allocation['device']}
                Compute type     : {device_allocation['compute_type']}
                Device index     : {device_allocation.get('device_index', 'N/A')}
                Instance index   : {instance_index}
                Model load time  : {time_taken:.2f} seconds
                Current pool size: {self.current_size}
                """
            )

        except Exception as e:
            self.logger.error(
                f"Failed to create and add model instance to the pool: {e}"
            )

    async def _destroy_model(self, model) -> None:
        """
        销毁模型实例并更新池大小。

        Destroy a model instance and update the pool size.

        :param model: 要销毁的模型实例 | The model instance to destroy
        """
        try:
            # 删除模型实例的引用 | Explicitly delete the model instance reference
            del model
            # 获取设备分配信息 | Get device allocation info
            device_allocation = self.allocate_device(self.current_size - 1, self.fast_whisper_device, self.engine)
            # 如果使用 GPU 则清理 CUDA 缓存 | Clear CUDA cache if using GPU
            if device_allocation["device"].startswith("cuda"):
                # 如果是单 GPU 系统，则清理整个 CUDA 缓存 | If it's a single GPU system, clear the entire CUDA cache
                if self.num_gpus == 1:
                    torch.cuda.empty_cache()
                    self.logger.info(f"CUDA cache cleared for device {device_allocation['device']} after model destruction.")
                else:
                    # 多 GPU 系统，则不进行清理，防止影响其他模型实例 | Multi-GPU system, do not clear to avoid affecting other model instances
                    self.logger.info(f"Skipping CUDA cache cleanup for multi-GPU system after model destruction.")
             # 执行垃圾回收 | Perform garbage collection on any device
            gc.collect()
            self.logger.info("Garbage collection performed after model destruction.")
            
            # 更新池大小，确保减少当前池大小 | Update pool size to reflect the reduced pool size
            async with self.size_lock:
                self.current_size = max(0, self.current_size - 1)
                self.logger.info(f"""
                Model instance destroyed successfully.
                Updated pool size: {self.current_size}
                Minimum pool size: {self.min_size}
                Maximum pool size: {self.max_size}
                """)
            
        except Exception as e:
            self.logger.error(f"Failed to destroy model instance: {str(e)}", exc_info=True)