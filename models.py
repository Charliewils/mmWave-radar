"""
mmWave 雷达协议数据模型（Pydantic）

定义 SYTC 协议帧结构：MircoHead、MircoBody、MircoCheck、MircoData、Serial 配置。
"""

from typing import List, Literal

from pydantic import BaseModel, Field


class MircoHead(BaseModel):
    start_signal: List[int] = Field(
        default=[0x53, 0x59, 0x54, 0x43],
        min_length=4,
        max_length=4,
        description="起始信号，固定为4字节：['S', 'Y', 'T', 'C'] 的 ASCII 值"
    )

    data_length: int = Field(
        default=0x00,
        ge=0x00, le=0xFF,
        description="数据长度，1字节（0x00 ～ 0xFF）"
    )

    mode: int = Field(
        default=0x00,
        ge=0x00, le=0xFF,
        description="工作模式，1字节。0x01: 向前宽域探测, 0x02: 背部探测, "
                    "0x03: 向前窄域, 0x04: 前向跟踪, 0x05: 双人监测"
    )

    time: List[int] = Field(
        default=[0x00, 0x00],
        min_length=2,
        max_length=2,
        description="测量时间，固定2字节，单位为分钟"
    )

    num_TLV: int = Field(
        default=0x00,
        ge=0x00, le=0xFF,
        description="雷达探测到呼吸心率人数"
    )
    work_con: int = Field(
        default=0x01,
        ge=0x01, le=0x03,
        description="雷达工作状态，1-正常，2-待机，3-异常"
    )
    reserve: List[int] = Field(
        default=[0x00, 0x00],
        min_length=2,
        max_length=2,
        description="保留字段，2字节，固定为0x00"
    )


class MircoBody(BaseModel):
    tlv_signal: int = Field(
        ge = 0, le = 2,
        description="TLV子帧标识，1字节，0x01: 第一个位置, 0x02: 第二个位置。何意味？"
    )
    target_distance: int = Field(
        description="目标距离，1字节，整型，0.1米精度，范围0～25.6米",
        ge=0,
        le=256
    )
    target_azimuth: int = Field(
        description="目标方位，1字节，整型，1°精度，范围-127° ～ 128°",
        ge=-127,
        le=128
    )
    current_status: Literal[0x01, 0x02] = Field(
        description="当前状态，1字节，0x01: 正常状态; 0x02: 目标异常状态"
    )
    respiration_value: int = Field(
        description="呼吸值，1字节，整型"
    )
    heart_rate_value: int = Field(
        description="心率值，1字节，整型"
    )
    respiration_curve: List[int] = Field(
        description="呼吸曲线，20字节，8bit整型数组，共20个值",
        min_length=20,
        max_length=20
    )
    heart_rate_curve: List[int] = Field(
        description="心率曲线，20字节，8bit整型数组，共20个值",
        min_length=20,
        max_length=20
    )


class MircoCheck(BaseModel):
    crc: List[int] = Field(
        description="CRC16 何意味？",
        min_length=2,
        max_length=2
    )
    zw: List[int] = Field(
        default=[0xEE, 0xEE],
        description="结束符，固定为2字节：0xEE 0xEE"
    )


class MircoData(BaseModel):
    header: MircoHead = Field(
        description="数据头部"
    )
    bodies: List[MircoBody] = Field(
        description="数据体，包含多个目标数据"
    )
    check: MircoCheck = Field(
        description="数据校验和结束符"
    )


class Serial(BaseModel):
    port: str = Field(
        description="串口号，例如 COM3"
    )
    baudrate: int = Field(
        default=115200,
        description="波特率，默认115200"
    )
    rate: int = Field(
        default=1,
        description="读取频率，单位Hz，默认1Hz"
    )
    data_signal: int = Field(
        default=8,
        description="数据位"
    )
    stop_signal: int = Field(
        default=1,
        description="停止位"
    )
