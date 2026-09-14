from __future__ import annotations

import base64
import json
import os

def load_config(file_path: str):
    assert file_path.endswith('json'), "The configuration file should be in JSON format."
    with open(file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

def set_config(file_path: str, field_name: str, field_value):
    """
    """
    # 1. 校验文件格式，与 load_config 保持一致。
    assert file_path.endswith('json'), "The configuration file should be in JSON format."

    try:
        # 2. 读取原有配置（文件不存在则初始化空字典）
        if os.path.exists(file_path):  # 若文件不存在，初始化空字典
            config = load_config(file_path)
        else:
            config = {}

        # 3. 修改/新增字段（核心逻辑）
        config[field_name] = field_value

        # 4. 将修改后的配置写回文件（格式化写入，ensure_ascii=False支持中文）
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)  # 使用 indent=4 格式化，并用 ensure_ascii=False 保留中文。
        print(f"閰嶇疆淇敼鎴愬姛锛氬瓧娈礫{field_name}]宸茶缃负[{field_value}]锛屾枃浠惰矾寰勶細{file_path}")

    except FileNotFoundError:
        # 处理文件路径不存在的情况（比如上级文件夹不存在）
        print(f"错误：文件路径不存在 → {file_path}")
    except json.JSONDecodeError:
        print(f"错误：文件不是有效的JSON格式 → {file_path}")
    except PermissionError:
        print(f"错误：没有权限写入文件 → {file_path}")
    except Exception as e:
        print(f"Unknown error: {e}")


def read_file(file_path: str):
    """
    Read the content of a file and return it as a string.
    """
    if file_path.endswith('txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    if file_path.endswith('csv'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.readlines()


def multi_chat(api_handler: APIHandler, prompt, history=None, max_completion_tokens=4096,enable_thinking = True):  # 定义大模型run的过程，涉及多轮对话 要有记忆
    """
    Multi-round chat with the assistant.
    """
    if history is None:
        history = []
    # 访问大模型服务获得返回结果
    messages = history + [{'role': 'user', 'content': prompt}]
    from sack.api_handler import APISettings

    settings = APISettings(max_completion_tokens=max_completion_tokens)
    reply = api_handler.get_output(messages=messages, settings=settings,enable_thinking=enable_thinking)

    # 记忆更新
    history.append({'role': 'user', 'content': prompt})
    history.append({'role': 'assistant', 'content': reply})

    return reply, history


def read_image(prompt, image_path):
    """
    Read the image and return the response.
    """

    # encode the image
    def encode_image(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    # Getting the base64 string
    base64_image = encode_image(image_path)
    from sack.api_handler import APIHandler, APISettings

    api_handler = APIHandler('qwen3-vl-flash')
    messages = [
        {"role": "system", "content": "You are a professional data analyst."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"{prompt}"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]
    settings = APISettings(max_completion_tokens=4096)
    reply = api_handler.get_output(messages=messages, settings=settings, response_type='image')
    return reply

