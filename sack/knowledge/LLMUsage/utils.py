import base64
import re
import json
import logging
from typing import Dict, Any, List
from sack.api_handler import APIHandler, APISettings
from sack.utils import multi_chat as sack_multi_chat

def load_config(file_path: str):
    assert file_path.endswith('json'), "The configuration file should be in JSON format."
    with open(file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config


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


def multi_chat(api_handler: APIHandler, prompt, history=None, max_completion_tokens=4096):  # 定义大模型run的过程，涉及多轮对话 要有记忆
    """
    Multi-round chat with the assistant.
    """
    return sack_multi_chat(api_handler, prompt, history, max_completion_tokens)


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
    api_handler = APIHandler('Qwen2.5-vl-7b-instruct-awq')
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


def parse_json_from_response(raw_reply: str) -> Dict[str, Any]:
    """浠庡ぇ妯″瀷鍝嶅簲涓彁鍙栧拰瑙ｆ瀽JSON鍐呭"""

    def try_json_loads(data: str) -> Dict[str, Any]:
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logging.error(f"JSON decoding error: {e}")
            print(data)
            return None

    raw_reply = raw_reply.strip()
    logging.info(f"Attempting to extract JSON from raw reply.")

    # 首先尝试直接匹配JSON代码块
    json_match = re.search(r'```json(.*?)```', raw_reply, re.DOTALL)
    if json_match:
        reply_str = json_match.group(1).strip()
        reply = try_json_loads(reply_str)
        if reply is not None:
            return reply

    # 濡傛灉娌℃湁浠ｇ爜鍧楋紝灏濊瘯鍖归厤鏁翠釜鍝嶅簲涓殑JSON瀵硅薄
    json_match = re.search(r'\{.*\}', raw_reply, re.DOTALL)
    if json_match:
        reply_str = json_match.group(0).strip()
        reply = try_json_loads(reply_str)
        if reply is not None:
            return reply

    # 濡傛灉鎻愬彇澶辫触锛岃繑鍥炵┖瀛楀吀
    logging.error("Failed to parse JSON from response")
    return {}

