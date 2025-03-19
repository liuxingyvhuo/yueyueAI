import socket
import os
import wave
import threading
import time
import requests
import json
import websocket
import datetime
import hashlib
import base64
import hmac
from urllib.parse import urlencode
import ssl
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
import _thread as thread

# 设置保存音频文件的目录
UPLOAD_FOLDER = 'udp_uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# UDP服务器配置
UDP_IP = "0.0.0.0"  # 监听所有可用接口
UDP_PORT = 12345  # 自定义端口号
AUDIO_UDP_PORT = 12347  # 新的音频传输端口

API_KEY = ""
SECRET_KEY = ""

QF_AUTHORIZATION = "Bearer "  # 请填写您的Authorization

# 科大讯飞相关配置
APPID = ''
APISecret = ''
APIKey = ''

STATUS_FIRST_FRAME = 0  # 第一帧的标识
STATUS_CONTINUE_FRAME = 1  # 中间帧标识
STATUS_LAST_FRAME = 2  # 最后一帧的标识

# 定义音频结束信号
AUDIO_END_SIGNAL = b'END_AUDIO'

class Ws_Param(object):
    # 初始化
    def __init__(self, APPID, APIKey, APISecret, Text):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.Text = Text

        # 公共参数(common)
        self.CommonArgs = {"app_id": self.APPID}
        # 业务参数(business)，更多个性化参数可在官网查看
        self.BusinessArgs = {"aue": "raw", "auf": "audio/L16;rate=16000", "vcn": "xiaoyan",
                             "speed": 30, "volume": 10, "pitch": 55, "tte": "utf8"}
        self.Data = {"status": 2, "text": str(base64.b64encode(self.Text.encode('utf-8')), "UTF8")}

    # 生成url
    def create_url(self):
        url = 'wss://tts-api.xfyun.cn/v2/tts'
        # 生成RFC1123格式的时间戳
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        # 拼接字符串
        signature_origin = "host: " + "ws-api.xfyun.cn" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/tts " + "HTTP/1.1"
        # 进行hmac-sha256进行加密
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
            self.APIKey, "hmac-sha256", "host date request-line", signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        # 将请求的鉴权参数组合为字典
        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        # 拼接鉴权参数，生成url
        url = url + '?' + urlencode(v)
        return url


def on_message(ws, message):
    try:
        message = json.loads(message)
        code = message["code"]
        sid = message["sid"]
        if "data" in message:
            audio = message["data"]["audio"]
            audio = base64.b64decode(audio)
            status = message["data"]["status"]
            if status == 2:
                print("ws is closed")
                ws.close()
            if code != 0:
                errMsg = message["message"]
                print("sid:%s call error:%s code is:%s" % (sid, errMsg, code))
            else:
                with open('./demo.pcm', 'ab') as f:
                    f.write(audio)
        else:
            print("Received message without 'data' key:", message)
    except Exception as e:
        print("receive msg,but parse exception:", e)


# 收到websocket错误的处理
def on_error(ws, error):
    print("### error:", error)


# 收到websocket关闭的处理
def on_close(ws, close_status_code, close_msg):
    print("### closed ###")


# 收到websocket连接建立的处理
def on_open(ws):
    def run(*args):
        d = {"common": wsParam.CommonArgs,
             "business": wsParam.BusinessArgs,
             "data": wsParam.Data,
             }
        d = json.dumps(d)
        print("------>开始发送文本数据")
        ws.send(d)
        if os.path.exists('./demo.pcm'):
            os.remove('./demo.pcm')

    thread.start_new_thread(run, ())


def synthesize_text(text):
    global wsParam
    wsParam = Ws_Param(APPID, APIKey, APISecret, text)
    websocket.enableTrace(False)
    wsUrl = wsParam.create_url()
    ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.on_open = on_open
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})


def receive_audio(sock, audio_frames, end_signal_received, lock, addr_list):
    try:
        while not end_signal_received.is_set():
            data, addr = sock.recvfrom(65535)  # 缓冲区大小为64KB
            print(f"Received packet from {addr}")

            if not data:
                print("No data received")
                continue

            # 检查是否为结束信号
            if data == b'END':
                print("End signal received")
                end_signal_received.set()
                break

            # 假设每次接收完整的音频帧，可以根据实际情况调整
            with lock:
                audio_frames.append(data)  # 存储接收到的音频帧
                addr_list.append(addr)  # 存储客户端地址
    except Exception as e:
        print(f"Error receiving audio: {e}")
    finally:
        sock.close()


def get_access_token():
    """
    使用 AK，SK 生成鉴权签名（Access Token）
    :return: access_token，或是None(如果错误)
    """
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
    response = requests.post(url, params=params)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print(f"Failed to get access token: {response.text}")
        return None


def recognize_audio(wav_path, token):
    url = "https://vop.baidu.com/server_api"
    with open(wav_path, 'rb') as audio_file:
        audio_data = audio_file.read()

    headers = {
        'Content-Type': 'audio/pcm; rate=16000'
    }

    data = {
        "format": "pcm",
        "rate": 16000,
        "channel": 1,
        "cuid": "yG6EA3oUSrRXRsoOdYNSdeyXZl37dd49",
        "token": token
    }

    response = requests.post(url, headers=headers, data=audio_data, params=data)

    if response.status_code == 200:
        result = response.json()
        if 'result' in result:
            return result['result'][0]
        else:
            print("No recognition result found:", result)
    else:
        print(f"Failed to recognize audio: {response.text}")
    return None


def call_qwen_model(conversation_history, user_text):
    conversation_history.append({"role": "user", "content": user_text})

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": "deepseek/deepseek-chat:free",
        "messages": conversation_history,
    }, ensure_ascii=False)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': QF_AUTHORIZATION
    }

    response = requests.request("POST", url, headers=headers, data=payload.encode("utf-8"))
    if response.status_code == 200:
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        print("Qwen Model Response Content:", content)
        conversation_history.append({"role": "assistant", "content": content})
        return content, conversation_history
    else:
        print(f"Failed to get response from Qwen model: {response.text}")
        return None, conversation_history

def send_audio_to_client(client_ip, client_audio_port):
    try:
        CHUNK_SIZE = 700  # 每个数据块的大小，可根据实际情况调整
        with open('./demo.pcm', 'rb') as f:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as audio_sock:
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break
                    audio_sock.sendto(data, (client_ip, client_audio_port))
                    time.sleep(0.01)  # 延迟 10 毫秒
                # 发送音频结束信号
                audio_sock.sendto(AUDIO_END_SIGNAL, (client_ip, client_audio_port))
                print(f"成功发送音频给 {client_ip}:{client_audio_port}")
    except Exception as e:
        print(f"发送音频时出错: {e}")


def main():
    conversation_history = [
        {
            "role": "system",
            "content": "你需要扮演一个大三清纯女友，你叫悦悦，是对方的初恋，性格温柔善解人意。接下来的对话里，根据对方的话语，自然地回应，展现出温柔体贴、活泼俏皮的一面，话题尽量围绕你们的日常生活、彼此感受展开，多用亲昵称呼，“航宝”。遇到需要解释的情况，语气要软，不要生硬；当对方分享日常时，要积极回应，表达兴趣和关心；对方提出计划时，要热情参与，提出自己的想法。"
        }
    ]

    while True:
        print(f"Starting UDP server on {UDP_IP}:{UDP_PORT}")

        # 创建UDP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((UDP_IP, UDP_PORT))

        audio_frames = []  # 用于存储接收到的音频帧
        end_signal_received = threading.Event()  # 标记是否收到结束信号
        lock = threading.Lock()  # 用于线程同步
        addr_list = []  # 用于存储客户端地址

        # 启动接收音频的线程
        receive_thread = threading.Thread(target=receive_audio, args=(sock, audio_frames, end_signal_received, lock, addr_list))
        receive_thread.start()

        try:
            while not end_signal_received.is_set():
                time.sleep(0.1)  # 适当延迟，避免频繁检查

            # 等待接收线程结束
            receive_thread.join()

            if end_signal_received.is_set():
                # 合并所有音频帧并保存到固定的文件中，覆盖上一次的文件
                combined_audio_path = os.path.join(UPLOAD_FOLDER, "combined_audio.pcm")
                with wave.open(combined_audio_path, 'wb') as combined_file:
                    # 设置音频参数
                    combined_file.setnchannels(1)  # 单声道
                    combined_file.setsampwidth(2)  # 16位
                    combined_file.setframerate(16000)  # 16000Hz
                    with lock:
                        for frame in audio_frames:
                            combined_file.writeframes(frame)
                print(f"Combined audio data saved to {combined_audio_path}")

                # 获取 access token
                token = get_access_token()
                if token:
                    # 调用百度语音识别API
                    recognized_text = recognize_audio(combined_audio_path, token)
                    if recognized_text:
                        # 打印识别出的文字
                        print(f"Recognized Text: {recognized_text}")
                        # 启动一个新的线程来调用大模型API
                        response_content, conversation_history = call_qwen_model(conversation_history, recognized_text)
                        if response_content:
                            # 发送回复内容给客户端
                            client_ip = ""  # 要设置客户端IP地址
                            client_port = 12346  # 客户端接收端口
                            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as new_sock:
                                new_sock.sendto(response_content.encode('utf-8'), (client_ip, client_port))
                                print(f"成功发送给 {client_ip}:{client_port}")

                            # 合成语音
                            synthesize_text(response_content)

                            # 发送音频给客户端
                            client_audio_port = 12348  # 客户端音频接收端口
                            send_audio_to_client(client_ip, client_audio_port)

                # 清空 audio_frames 列表，准备接收新的音频数据
                with lock:
                    audio_frames.clear()
                    addr_list.clear()  # 清空 addr_list，确保只发送一次
            else:
                print("No end signal received, no audio data combined.")
        except KeyboardInterrupt:
            print("Server stopped by user")
            break
        finally:
            end_signal_received.set()
            receive_thread.join()
            sock.close()  # 确保在所有操作完成后关闭套接字


if __name__ == "__main__":
    main()