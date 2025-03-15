from machine import Pin, I2S, SPI
import network
import time
import socket
import os
import _thread
import ufont
from st7735 import ST7735
import gc 


spi = SPI(1, 20000000, sck=Pin(4), mosi=Pin(16))
display = ST7735(spi=spi, cs=18, dc=5, rst=17, bl=19, width=160, height=128, rotate=1)

font = ufont.BMFont("new.bmf")

# Wi-Fi 信息
ssid = ''#你wifi名
password = ''#你的wifi密码

wlan = network.WLAN(network.STA_IF)

# 全局变量，用于标记网络是否连接成功
network_connected = False

# 定义四脚微动开关的引脚，这里假设使用 GPIO13 作为开关引脚
button_pin = Pin(13, Pin.IN, Pin.PULL_UP)

# 定义 INMP441 的引脚
sd_inmp441 = Pin(23)
sck_inmp441 = Pin(22)
ws_inmp441 = Pin(21)

# 定义 MAX98357 的引脚
lrc_max98357 = Pin(12)
bclk_max98357 = Pin(14)
din_max98357 = Pin(27)

# 服务器地址和端口
server_ip = ""#你的服务端ip地址
server_port = 12345

# 全局变量 recording 和锁
recording = False
recording_lock = _thread.allocate_lock()
# 定义音频结束信号
AUDIO_END_SIGNAL = b'END_AUDIO'

# 客户端接收端口
client_port = 12346
# 客户端接收音频端口
client_audio_port = 12348


def connect_wifi():
    global network_connected
    # 未连接时显示等待连接
    font.text(display, "等待连接", 0, 0, show=True, clear=True, font_size=12)
    print(f"连接 Wi-Fi 前可用内存: {gc.mem_free()} 字节")  # 检查连接 Wi-Fi 前的内存

    wlan.active(True)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect(ssid, password)
        timeout = 10  # 连接超时时间，单位为秒
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
        if not wlan.isconnected():
            print("连接 Wi-Fi 失败")
            return
    print('连接成功。网络配置:', wlan.ifconfig())
    # 连接成功后显示网络 ok
    font.text(display, "网络ok", 0, 0, show=True, clear=True, font_size=12)
    font.text(display, "\(^_^)/", 25, 20, show=True, font_size=30)
    font.text(display, "你好呀！", 0, 60, show=True, font_size=16)
    font.text(display, "我是你的悦悦公主！", 0, 80, show=True, font_size=16)
    network_connected = True

def print_memory_usage():
    """打印当前的内存使用情况"""
    free_memory = gc.mem_free()
    allocated_memory = gc.mem_alloc()
    total_memory = free_memory + allocated_memory
    print(f"Free memory: {free_memory} bytes, Allocated memory: {allocated_memory} bytes, Total memory: {total_memory} bytes")

def send_audio_to_server(audio_in, send_buffer):
    global recording
    try:
        # 创建UDP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)  # 设置超时时间

        while True:
            with recording_lock:
                if not recording:
                    break
            num_read = audio_in.readinto(send_buffer)
            print_memory_usage()
            if num_read > 0:
                sock.sendto(send_buffer[:num_read], (server_ip, server_port))
            time.sleep(0.01)  # 减少延迟，确保及时检测 recording 变量的变化

        # 发送结束信号
        sock.sendto(b'END', (server_ip, server_port))
        print("End signal sent to server")
        sock.close()
    except Exception as e:
        print("Error sending audio to server:", e)

def receive_response_from_server():
    try:
        # 创建 UDP 套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', client_port))
        print(f"Listening for responses on port {client_port}")

        while True:
            data, addr = sock.recvfrom(3072)  # 缓冲区大小为 3072 字节
            print(f"Received response from {addr}: {data.decode('utf-8')}")

            # 解码数据
            decoded_data = data.decode('utf-8')
            # 按每 10 个字符进行换行处理
            wrapped_lines = []
            for i in range(0, len(decoded_data), 10):
                wrapped_lines.append(decoded_data[i:i + 10])
            wrapped_text = '\n'.join(wrapped_lines)

            # 按每 5 行一组进行处理
            lines = wrapped_text.split('\n')
            for i in range(0, len(lines), 5):
                group = lines[i:i + 5]
                group_text = '\n'.join(group)

                # 显示在屏幕上
                font.text(display, group_text, 0, 20, show=True, clear=True, font_size=16)

                # 每组内容显示后暂停 3 秒
                time.sleep(5)

            # 打印成功接收
            print("成功接收")
            sock.close()
            break  # 接收一次后退出循环

    except Exception as e:
        print("Error receiving response from server:", e)

def receive_audio_from_server(audio_out):
    try:
        # 创建 UDP 套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', client_audio_port))
        print(f"Listening for audio on port {client_audio_port}")

        while True:
            data, addr = sock.recvfrom(700)  # 缓冲区大小为 4096 字节
            if data == AUDIO_END_SIGNAL:
                print("Received audio end signal, stopping audio reception.")
                break
            print(f"Received audio data from {addr}")
            audio_out.write(data)  # 播放音频数据

    except Exception as e:
        print("Error receiving audio from server:", e)
    finally:
        sock.close()
        print("Audio reception thread ended.")

def debounce_button(button_pin, debounce_time=50):
    current_state = button_pin.value()
    start_time = time.ticks_ms()
    
    while time.ticks_diff(time.ticks_ms(), start_time) < debounce_time:
        if button_pin.value() != current_state:
            return False
    
    return True

def main():
    global recording
    # 启动一个新线程来连接网络
    connect_wifi()   
    
    # 等待网络连接成功
    while not network_connected:
        time.sleep(0.1)

    # 配置 I2S 接口
    audio_in = I2S(0,
                   sck=sck_inmp441,
                   ws=ws_inmp441,
                   sd=sd_inmp441,
                   mode=I2S.RX,
                   bits=16,
                   format=I2S.MONO,
                   rate=16000,
                   ibuf=6000)  # 增加内部缓冲区大小
    
    audio_out = I2S(1,
                  sck=bclk_max98357,
                  ws=lrc_max98357,
                  sd=din_max98357,
                  mode=I2S.TX,
                  bits=16,
                  format=I2S.MONO,
                  rate=16000,
                  ibuf=6000)

    audio_buffer = bytearray(700)  # 用于 I2S 收集音频数据
    send_buffer = bytearray(1000)   # 用于发送数据到服务器
    press_start_time = None  # 记录按键按下的开始时间
    long_press_threshold = 100  # 长按的时间阈值，单位为毫秒

   

    while True:
        button_state = button_pin.value()

        if button_state == 0 and debounce_button(button_pin):  # 按键被按下
            if press_start_time is None:
                press_start_time = time.ticks_ms()  # 记录按下开始时间
            elif time.ticks_diff(time.ticks_ms(), press_start_time) >= long_press_threshold:
                # 长按按键，显示 (~_~)
                font.text(display, "听(~_~)听", 25, 2, show=True, clear=True, font_size=25)
                with recording_lock:
                    if not recording:
                        recording = True
                        print("开始采集音频")
                        print(f"连接 采集 前可用内存: {gc.mem_free()} 字节")  # 检查连接 Wi-Fi 前的内存
                        _thread.start_new_thread(send_audio_to_server, (audio_in, send_buffer))
        else:  # 按键被松开
            if press_start_time is not None:
                press_start_time = None  # 重置按下开始时间
                # 松开按键，显示 (^_^)
                font.text(display, "(^_^)", 50, 2, show=True, clear=True, font_size=25)
                # 启动一个新线程来接收服务器响应
                _thread.start_new_thread(receive_response_from_server, ())
                 # 启动一个新线程来接收音频
                _thread.start_new_thread(receive_audio_from_server, (audio_out,))
            with recording_lock:
                if recording:
                    recording = False
                    print("停止采集音频")

        time.sleep(0.01)  # 适当的延迟，避免频繁读取按键状态

if __name__ == "__main__":
    main()
