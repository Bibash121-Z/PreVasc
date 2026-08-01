# ==========================================================
# serial_reader.py
# Handles serial communication with the ESP32
# ==========================================================

import serial
import threading
import numpy as np
from collections import deque
import time


class SerialReader:

    # Initialize serial reader
    def __init__(
        self,
        port="COM10",
        baudrate=115200,
        buffer_size=1000
    ):

        self.port = port
        self.baudrate = baudrate

        # Circular buffer for PPG samples
        self.buffer = deque(maxlen=buffer_size)

        # Circular buffer for timestamps
        self.timestamps = deque(maxlen=buffer_size)

        self.serial = None
        self.thread = None

        # Thread control flag
        self.running = False

        # Synchronize buffer access
        self.lock = threading.Lock()

    # --------------------------------------------------

    # Connect to ESP32
    def connect(self):

        try:

            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=1
            )

            # Wait for ESP32 reset
            time.sleep(2)

            print(f"Connected to {self.port}")

            return True

        except Exception as e:

            print(f"Connection Error: {e}")

            return False

    # --------------------------------------------------

    # Start background thread
    def start(self):

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self.read_serial,
            daemon=True
        )

        self.thread.start()

    # --------------------------------------------------

    # Stop background thread
    def stop(self):

        self.running = False

        if self.thread is not None:
            self.thread.join()

        if self.serial is not None:
            self.serial.close()

    # --------------------------------------------------

    # Read incoming serial data
    def read_serial(self):

        while self.running:

            try:

                line = self.serial.readline().decode(
                    "utf-8",
                    errors="ignore"
                ).strip()

                if not line:
                    continue

                # Expected format:
                # timestamp,ppg
                try:

                    timestamp, value = line.split(",")

                    timestamp = float(timestamp)
                    value = float(value)

                except ValueError:
                    continue

                with self.lock:

                    self.timestamps.append(timestamp)
                    self.buffer.append(value)

            except Exception:
                continue

    # --------------------------------------------------

    # Return PPG samples
    def get_data(self):

        with self.lock:

            return np.array(
                self.buffer,
                dtype=float
            )

    # --------------------------------------------------

    # Return timestamps
    def get_timestamps(self):

        with self.lock:

            return np.array(
                self.timestamps,
                dtype=float
            )

    # --------------------------------------------------

    # Return both timestamps and PPG
    def get_all_data(self):

        with self.lock:

            return (
                np.array(self.timestamps, dtype=float),
                np.array(self.buffer, dtype=float)
            )

    # --------------------------------------------------

    # Clear buffers
    def clear(self):

        with self.lock:

            self.timestamps.clear()
            self.buffer.clear()

    # --------------------------------------------------

    # Return current buffer size
    def sample_count(self):

        with self.lock:

            return len(self.buffer)

    # --------------------------------------------------

    # Check connection status
    def is_connected(self):


        return (
            self.serial is not None and
            self.serial.is_open
        )