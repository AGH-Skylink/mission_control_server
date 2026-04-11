import numpy as np
from multiprocessing import shared_memory


class RingBuffer:
    """Implements the ring audio buffer, for safety reasons only one process should read from it and only one write to it"""

    def __init__(self, shm_package: dict):
        self.buffer_size = shm_package["buffer_size"]
        self.frame_size = shm_package["frame_size"]
        self.shm_memory = shared_memory.SharedMemory(name=shm_package["memory_name"])
        self.dtype = shm_package["dtype"]
        self.memory = np.ndarray((self.buffer_size, self.frame_size), dtype=self.dtype, buffer=self.shm_memory.buf)
        self.read_flag = shm_package["read_flag"]  # flag is incremented, next data is read
        self.read_lock = shm_package["read_lock"]
        self.write_flag = shm_package["write_flag"]  # data is written, next flag is incremented
        self.write_lock = shm_package["write_lock"]
        self.reset()

    def reset(self) -> None:
        """Resets the ring buffer."""
        with self.write_lock:
            with self.read_lock:
                self.read_flag = 0
                self.write_flag = 1

    def memory_name(self) -> str:
        """Returns the name of shared memory used by the ring buffer."""
        return self.shm_memory.name

    def empty(self) -> bool:
        """Checks if the ring buffer is empty."""
        with self.write_lock:
            with self.read_lock:
                return self.write_flag == (self.read_flag + 1) % self.buffer_size

    def full(self) -> bool:
        """Checks if the ring buffer is full."""
        with self.write_lock:
            with self.read_lock:
                return self.read_flag == self.write_flag

    def get(self) -> np.ndarray:
        """Takes the element from the ring buffer. If empty, raises an Exception."""
        if self.empty():
            raise Exception(f"Buffer empty")
        with self.read_lock:
            self.read_flag = (self.read_flag + 1) % self.buffer_size
            print(self.read_flag)
        memory_copy = self.memory[self.read_flag, :].copy()
        return memory_copy

    def put(self, data: np.ndarray, regardless: bool = False) -> None:
        """Places the element into the ring buffer. If full, raises an Exception or overwrites the other element.
        :param data: The data to be put into the ring buffer.
        :type data: np.ndarray
        :param regardless: if True, in case of full buffer, the latest element is overwritten."""
        if self.full():
            if regardless:
                self.memory[self.read_flag, :] = data
                return
            raise Exception(f"Buffer full")
        self.memory[self.read_flag, :] = data
        with self.write_lock:
            self.write_flag = (self.write_flag + 1) % self.buffer_size
