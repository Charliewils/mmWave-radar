# python
"""
OOP 串口读取示例
- 使用 `Serial` 配置模型（来自 `models.py`）
- 提供 `SerialReader` 类用于打开/关闭串口并循环读取（文本或二进制帧）
- 提供 `MircoParser` 类用于根据 `models` 中定义的协议解析二进制帧

说明：
- 需安装依赖：pip install pyserial pydantic
- 协议要点（中文说明）：
  - 起始信号：4 字节，固定为 0x53 0x59 0x54 0x43（ASCII 'S','Y','T','C')
  - header 中的 `time` 字段固定为 2 字节（单位：分钟）
  - data_length: 1 字节，通常表示 body 区域的字节长度
  - num_TLV: 1 字节，表示后续 body 的个数
  - 每个 body 固定 46 字节，包含 tlv 标识、距离、方位、状态、呼吸/心率值与各自的 20 字节曲线
  - 校验区：crc (2 字节) + 结束符 zw (2 字节，固定为 0xEE 0xEE)

串口配置模型新增字段说明：
- `start_signal`：数据位，整型，通常为 5/6/7/8，默认 8
- `stop_signal`：停止位，整型，通常为 1 或 2，默认 1

备注：如果协议细节（如 CRC 算法或字段长度）与实际设备不同，请根据设备文档调整 `MircoParser` 中的偏移和大小。
"""

import time
import json
import serial
import serial.tools.list_ports
import numpy as np
from collections import deque
from typing import Callable, List, Optional, cast, Literal as TyLiteral
from threading import Thread, Lock, Event
import queue
from models import Serial as SerialConfig
from models import MircoHead, MircoBody, MircoCheck, MircoData
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import queue
from datetime import datetime, timedelta



class MircoParser:
    """解析器：从串口中查找帧起始符并解析完整帧为 Pydantic 模型"""
    START_SEQ = bytes([0x53, 0x59, 0x54, 0x43])
    BODY_SIZE = 46

    @staticmethod
    def read_exact(ser: serial.Serial, size: int, timeout: Optional[float] = None) -> bytes:
        """从串口读取精确的字节数，允许短读并在超时后返回已读数据"""
        buf = bytearray()
        start = time.time()
        while len(buf) < size:
            to_read = size - len(buf)
            chunk = ser.read(to_read)
            if chunk:
                buf.extend(chunk)
            else:
                if timeout is not None and (time.time() - start) > timeout:
                    break
                time.sleep(0.01)
        return bytes(buf)

    @classmethod
    def find_start(cls, ser: serial.Serial, timeout: float = 1.0) -> bool:
        """在串口数据流中查找起始序列，找到返回 True，超时返回 False"""
        window = bytearray()
        start_time = time.time()
        while True:
            b = ser.read(1)
            if not b:
                if (time.time() - start_time) > timeout:
                    return False
                continue
            window += b
            if len(window) > len(cls.START_SEQ):
                window.pop(0)
            if bytes(window) == cls.START_SEQ:
                return True

    @classmethod
    def parse_frame_from_serial(cls, ser: serial.Serial, timeout: float = 1.0) -> Optional[MircoData]:
        """从串口解析并返回一个完整的 MircoData 对象，失败或超时返回 None"""
        found = cls.find_start(ser, timeout=timeout)
        if not found:
            return None

        header_remain = cls.read_exact(ser, 1 + 1 + 2 + 1 + 1 + 2, timeout=timeout)
        if len(header_remain) < 8:
            return None

        data_length = header_remain[0]
        mode = header_remain[1]
        time_field = list(header_remain[2:4])
        num_TLV = header_remain[4]
        work_con = header_remain[5]
        reserve = list(header_remain[6:8])

        expected_bodies_bytes = num_TLV * cls.BODY_SIZE
        bodies_bytes = cls.read_exact(ser, expected_bodies_bytes, timeout=timeout)
        if len(bodies_bytes) < expected_bodies_bytes:
            return None

        bodies: List[MircoBody] = []
        offset = 0
        for i in range(num_TLV):
            chunk = bodies_bytes[offset: offset + cls.BODY_SIZE]
            if len(chunk) < cls.BODY_SIZE:
                return None
            tlv_signal = chunk[0]
            target_distance = chunk[1]
            target_azimuth = chunk[2]
            current_status = chunk[3]
            respiration_value = chunk[4]
            heart_rate_value = chunk[5]
            respiration_curve = list(chunk[-44: -24])
            heart_rate_curve = list(chunk[-24 : -4])

            body = MircoBody(
                tlv_signal=cast(TyLiteral[1, 2], 1 if tlv_signal == 0 else tlv_signal),
                target_distance=target_distance,
                target_azimuth=target_azimuth if target_azimuth <= 127 else target_azimuth - 256,
                current_status=cast(TyLiteral[0x01, 0x02], current_status),
                respiration_value=respiration_value,
                heart_rate_value=heart_rate_value,
                respiration_curve=respiration_curve,
                heart_rate_curve=heart_rate_curve,
            )
            bodies.append(body)
            offset += cls.BODY_SIZE

        check_bytes = cls.read_exact(ser, 4, timeout=timeout)
        if len(check_bytes) < 4:
            return None
        crc = [check_bytes[0], check_bytes[1]]
        zw = [check_bytes[2], check_bytes[3]]

        header = MircoHead(
            start_signal=list(cls.START_SEQ),
            data_length=data_length,
            mode=mode,
            time=time_field,
            num_TLV=num_TLV,
            work_con=work_con,
            reserve=reserve,
        )
        check = MircoCheck(crc=crc, zw=zw)
        data = MircoData(header=header, bodies=bodies, check=check)
        
        # 返回数据和解析的头部信息
        return data, {
            'data_length': data_length,
            'mode': mode,
            'time_minutes': time_field[0] + (time_field[1] << 8),  # 将2字节转换为分钟数
            'num_targets': num_TLV,
            'work_status': work_con,
            'reserve': reserve
        }





class SerialReader:
    """面向对象的串口读取器"""
    def __init__(self, config: SerialConfig, line_mode: bool = True):
        self.config = config
        self.line_mode = line_mode
        self.ser: Optional[serial.Serial] = None
        
     
        
    @staticmethod
    def list_ports() -> List[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

    def open(self) -> None:
        if self.ser and self.ser.is_open:
            return
            
        bs_map = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS,
        }
        sb_map = {
            1: serial.STOPBITS_ONE,
            2: serial.STOPBITS_TWO,
        }
        
        try:
            bytesize = bs_map.get(int(self.config.data_signal), serial.EIGHTBITS)
        except Exception:
            bytesize = serial.EIGHTBITS
            
        try:
            stopbits = sb_map.get(int(self.config.stop_signal), serial.STOPBITS_ONE)
        except Exception:
            stopbits = serial.STOPBITS_ONE

        self.ser = serial.Serial(
            port=self.config.port,
            baudrate=self.config.baudrate,
            timeout=1,
            bytesize=bytesize,
            stopbits=stopbits,
        )

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
        

 

    def _format_header_info(self, header_data):
        """格式化头部信息为可读字符串"""
        mode_map = {
            1: "Forward Wide Area",
            2: "Back Detection", 
            3: "Forward Narrow Area",
            4: "Forward Tracking",
            5: "Dual Person Monitoring"
        }
        
        status_map = {
            1: "Normal",
            2: "Standby",
            3: "Abnormal"
        }
        
        mode_str = mode_map.get(header_data['mode'], f"Unknown({header_data['mode']})")
        status_str = status_map.get(header_data['work_status'], f"Unknown({header_data['work_status']})")
        
        return (f"Data Length: {header_data['data_length']} bytes, "
                f"Mode: {mode_str}, "
                f"Time: {header_data['time_minutes']} mins, "
                f"Targets: {header_data['num_targets']}, "
                f"Status: {status_str}, "
                f"Reserve: {header_data['reserve']}")

    

    def read_loop(self, callback: Optional[Callable[[str], None]] = None) -> None:
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port not opened")

        print(f"Opened {self.config.port}, press Ctrl+C to exit. Mode: {'Text' if self.line_mode else 'Binary'}")
        
        # 创建数据队列
        data_queue = queue.Queue()
        
        # 在单独的线程中处理串口数据
        def serial_read_thread():
            try:
                all_data = bytearray()
                import csv
                
                while True:
                    data = self.ser.read(1024)
                    if data:
                        all_data.extend(data)
                        
                        # 处理接收到的数据
                        while True:
                            # 查找 EE EE 的位置
                            ee_found = False
                            
                            for i in range(len(all_data) - 1):
                                if all_data[i] == 0xEE and all_data[i+1] == 0xEE:
                                    # 提取帧
                                    frame = all_data[:i+2]
                                    
                                    # 输出帧，每65个字节为一组
                                    for j in range(0, len(frame), 65):
                                        chunk = frame[j:j+65]
                                        hex_str = ' '.join(f'{byte_val:02X}' for byte_val in chunk)
                                        print(hex_str)
                                    
                                    # 提取第42-61个字节作为心率曲线数据
                                    if len(frame) >= 61:
                                        # 获取第42-61个字节（索引41-60）
                                        hr_data = frame[41:61]
                                        
                                        # 保存为CSV
                                        timestamp = datetime.now().strftime("%H_%M_%S")
                                        filename = "data.csv"
                            
                                        with open(filename, 'a', newline='') as f:
                                            writer = csv.writer(f)
                                            #writer.writerow(['Index', 'Hex_Value'])
                                            for idx, val in enumerate(hr_data, 1):
                                                hex_val = f'{val:02X}'
                                                writer.writerow([idx, hex_val])
                                        with open('average1.csv', 'a', newline='') as f:
                                            writer = csv.writer(f)
                                            writer.writerow([int(frame[20])])
                                           
                                        print(f"数据: {' '.join(f'{b:02X}' for b in hr_data)}")
                                        print('\n')
                                        
                                        # 将数据放入队列
                                        current_time = datetime.now()
                                        for idx, val in enumerate(hr_data):
                                            int_val = val
                                            if int_val >= 128:
                                                int_val = int_val - 256
                                            point_time = current_time + timedelta(seconds=idx*0.05)
                                            data_queue.put((int_val, point_time))
                                    
                                    # 移除已处理的帧
                                    all_data = all_data[i+2:]
                                    ee_found = True
                                    break
                            
                            if not ee_found:
                                break
                                
            except Exception as e:
                print(f"Serial read error: {e}")
                data_queue.put(('ERROR', None))
        
        # 启动串口读取线程
        serial_thread = threading.Thread(target=serial_read_thread, daemon=True)
        serial_thread.start()
        
        # 创建Tkinter窗口（在主线程中）
        root = tk.Tk()
        root.title("Heart Rate Monitor - Real Time")
        root.geometry("900x500")
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.set_title("Heart Rate - Real Time")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Heart Rate Value")
        ax.grid(True, alpha=0.3)
        
        # 初始化数据
        heart_rate_data = []
        times = []
        
        # 将图表嵌入Tkinter
        canvas = FigureCanvasTkAgg(fig, master=root)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 状态标签
        status_frame = tk.Frame(root)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(status_frame, text="Status:", font=("Arial", 10)).pack(side=tk.LEFT)
        status_label = tk.Label(status_frame, text="Waiting for data...", font=("Arial", 10), fg="blue")
        status_label.pack(side=tk.LEFT, padx=10)
        
        tk.Label(status_frame, text="Points:", font=("Arial", 10)).pack(side=tk.LEFT)
        points_label = tk.Label(status_frame, text="0", font=("Arial", 10))
        points_label.pack(side=tk.LEFT, padx=10)
        
        # 控制按钮
        def stop_program():
            self.close()
            root.quit()
        
        button_frame = tk.Frame(root)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(button_frame, text="Stop", command=stop_program, width=10).pack(side=tk.RIGHT)
        
        # 更新图表函数
        def update_plot():
            try:
                # 处理队列中的数据
                new_data_count = 0
                while not data_queue.empty():
                    item = data_queue.get_nowait()
                    if item == ('ERROR', None):
                        status_label.config(text="Serial Error", fg="red")
                        break
                    
                    hr_value, point_time = item
                    heart_rate_data.append(hr_value)
                    times.append(point_time)
                    new_data_count += 1
                
                # 只保留最近30秒的数据
                max_points = 600  # 30秒 * 20Hz
                if len(heart_rate_data) > max_points:
                    heart_rate_data[:] = heart_rate_data[-max_points:]
                    times[:] = times[-max_points:]
                
                # 更新图表
                if heart_rate_data:
                    ax.clear()
                    
                    # 计算相对时间
                    if times:
                        start_time = times[-1] - timedelta(seconds=min(30, len(heart_rate_data)/20))
                        relative_times = [(t - start_time).total_seconds() 
                                        for t in times[-len(heart_rate_data):]]
                    else:
                        relative_times = list(range(len(heart_rate_data)))
                    
                    # 绘制曲线
                    ax.plot(relative_times, heart_rate_data, 'b-', linewidth=2)
                    ax.set_title(f"Heart Rate - Real Time (Last {min(30, len(heart_rate_data)/20):.1f}s)")
                    ax.set_xlabel("Time (seconds)")
                    ax.set_ylabel("Heart Rate Value")
                    ax.grid(True, alpha=0.3)
                    
                    # 更新状态
                    if heart_rate_data:
                        current = heart_rate_data[-1]
                        avg_10s = sum(heart_rate_data[-200:])/min(200, len(heart_rate_data))  # 10秒平均
                        status_label.config(text=f"Current: {current} | Avg (10s): {avg_10s:.1f}", fg="green")
                        points_label.config(text=str(len(heart_rate_data)))
                    
                    if new_data_count > 0:
                        canvas.draw()
                
            except Exception as e:
                print(f"Update error: {e}")
            
            # 继续更新
            root.after(100, update_plot)
        
        # 开始更新
        update_plot()
        
        # 窗口关闭处理
        def on_closing():
            print("\nClosing window...")
            self.close()
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        try:
            # 运行Tkinter主循环
            root.mainloop()
            
        except KeyboardInterrupt:
            print("\nUser interrupted, exiting.")
        finally:
            self.close()
            print("Serial port closed.")
def main():
 
    config={
        'port':"COM3",
        'baudrate':115200,
        'rate':1,
        'data_signal':8,
        'stop_signal':1

    }
    # cfg = SerialConfig(port=port, baudrate=115200, rate=1, data_signal=data_bits, stop_signal=stop_bits)
    cfg = SerialConfig(**config)
    # reader = SerialReader(cfg, line_mode=line_mode)
    reader = SerialReader(cfg, line_mode=1)
    try:
        reader.open()
    except Exception as e:
        print("Failed to open serial port:", e)
        return



    reader.read_loop()


if __name__ == '__main__':
    main()