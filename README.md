# mmWave 毫米波雷达心率监测

基于77G毫米波雷达(R77ABH1 呼吸心跳雷达)的串口数据读取与心率曲线实时可视化工具。适用于支持 SYTC 协议的 mmWave 雷达模块（呼吸/心率检测,本代码以心跳模块为例）。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 功能特性

- **串口通信**：支持可配置波特率、数据位、停止位
- **协议解析**：解析 SYTC 格式二进制帧（`MircoParser`）
- **实时曲线**：Tkinter + Matplotlib 实时显示心率曲线（每帧 20 点）
- **数据导出**：自动将心率数据追加写入 `data.csv`、`average.csv`

## 环境要求

- Python 3.7+
- 毫米波雷达模块（支持 SYTC 协议）
- 串口连接（USB 转串口或板载串口）

## 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/mmWave.git
cd mmWave

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

> **说明**：`tkinter` 通常随 Python 自带。若提示缺失，请通过系统包管理器安装（如 Ubuntu: `sudo apt install python3-tk`）。

## 快速开始

```bash
# 列出可用串口
python demo.py -l

# 使用默认串口 COM3 启动（Windows）
python demo.py



## 命令行参数

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `--port` | `-p` | COM3 | 串口号 |
| `--baudrate` | `-b` | 115200 | 波特率 |
| `--list-ports` | `-l` | - | 列出可用串口后退出 |

## 协议说明

- **起始信号**：4 字节 `0x53 0x59 0x54 0x43`（ASCII "SYTC"）
- **Header**：包含 `data_length`、`mode`、`time`、`num_TLV`、`work_con`、`reserve`
- **Body**：每帧 46 字节，含 tlv 标识、距离、方位、状态、呼吸/心率值及 20 字节呼吸曲线、20 字节心率曲线
- **校验**：CRC (2 字节) + 结束符 `0xEE 0xEE`

若协议细节（如 CRC 或字段布局）与实际设备不符，请根据设备文档调整 `MircoParser` 及 `models.py`。

## 项目结构

```
mmWave/
├── demo.py       # 主程序：串口读取、解析、GUI 可视化
├── models.py     # 数据模型（Pydantic）：协议结构定义
├── requirements.txt
├── LICENSE       # MIT 协议
└── README.md
```

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。
