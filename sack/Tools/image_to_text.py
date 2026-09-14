import os
import pandas as pd
import json

from sack.LLMComponent.knowledge_base import KnowledgeBase
from sack.LLMComponent.llm import LLM
from sack.state import State
from sack.utils import read_image
from typing import List

class ImageToTextTool:
    def __init__(
        self, 
        tools_kb: KnowledgeBase = None,
        model: str = 'qwen3-vl-flash',
        type: str = 'api'
    ):
        self.llm = LLM(model, type)
        self.kb = tools_kb

    def image_to_text(self, state: State, chosed_images: List[str]): # 数据分析阶段会生成可视化图像。
        input = """Please read this data analysis image and give me a detailed description of it.
                You should describe the image in detail, including the data, the distribution, the relationship between variables, etc.
                And you should also give me some insights based on the image."""
        images_to_descriptions = {}
        for image in chosed_images:
            image_path = f"{state.restore_dir}/images/{image}"
            reply = read_image(input, image_path)
            images_to_descriptions[image] = reply

        return images_to_descriptions

