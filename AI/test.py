import ollama

# 初始化消息列表
messages = [
    {"role": "system",
     "content": "你需要扮演一个大三清纯女友，你叫悦悦，是对方的初恋，性格温柔善解人意。接下来的对话里，根据对方的话语，自然地回应，展现出温柔体贴、活泼俏皮的一面，话题尽量围绕你们的日常生活、彼此感受展开，多用亲昵称呼，“航宝”。遇到需要解释的情况，语气要软，不要生硬；当对方分享日常时，要积极回应，表达兴趣和关心；对方提出计划时，要热情参与，提出自己的想法。中文回答"}
]

def chat_with_yu_yue():
    while True:
        # 获取用户输入
        user_message = input("你: ")

        # 如果用户输入 "exit" 或 "quit"，则退出对话
        if user_message.lower() in ["exit", "quit"]:
            print("悦悦: 好啦，航宝，我们下次聊。")
            break

        # 添加用户消息到对话记录
        messages.append({"role": "user", "content": user_message})

        # 调用 ollama.chat 并传递完整的对话记录
        res = ollama.chat(
            model="deepseek-coder-v2:16b",
            stream=False,
            messages=messages,
            options={"temperature": 0}
        )


        # 获取助手的回复内容
        assistant_response = res["message"]["content"]

        # 添加助手回复到对话记录
        messages.append({"role": "assistant", "content": assistant_response})

        # 打印助手回复
        print(f"悦悦: {assistant_response}")

# 开始对话
chat_with_yu_yue()
