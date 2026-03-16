import re
import qrcode
from pathlib import Path
from typing import Dict, Any, Optional
import json

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from PIL import Image
import pdb
from src.state.poster_state import PosterState
from utils.src.logging_utils import log_agent_info, log_agent_success, log_agent_error
from src.config.poster_config import load_config

class Renderer:
    """ 渲染器类，用于设置结构布局，同时根据布局渲染海报 """

    def __init__(self):
        self.name = "renderer"
        # load configuration
        self.config = load_config()

    def __call__(self, state: PosterState) -> PosterState:
        """ 一个叫posterlayout,一个叫sectionlayout """
        # load sections information
        section_info = state["story_board"]#这里应该时story_board的数据
        # load poster layout data
        resource_dir = Path(state["resource_dir"])
        layout_dir = resource_dir / "poster_layouts"
        layout_dir.mkdir(parents=True, exist_ok=True)
        # 选取合适的poster_layout
        poster_layouts_file = layout_dir / "poster_layouts.json"
        print("start_select_poster_layout")
        poster_layout, sorted_area = self._select_poster_layout(state, section_info, poster_layouts_file)
        self._save_poster_layout_info(state, poster_layout, sorted_area)

        print("start_set_layout")
        sections_layout = self._set_layout(section_info, poster_layout, sorted_area)
        self._save_section_layout(state, sections_layout)

        # render poster
        print("start_render_poster")
        self.render_poster(state, sections_layout)

        return state
    
    def _save_poster_layout_info(self, state: PosterState, poster_layout: Dict, sorted_area: Dict):
        layout_info = {}
        layout_info["poster_layout"] = poster_layout
        layout_info["sorted_area"] = sorted_area
        output_dir = Path(state["output_dir"])
        with open(output_dir/"content"/"layout_sorted_by_area_info.json", "w", encoding="utf-8") as f:
            json.dump(layout_info, f, indent=2)

    def _save_section_layout(self, state: PosterState, sections_layout: Dict):
        output_dir = Path(state["output_dir"])
        with open(output_dir / "content" / "sections_layout.json", "w", encoding="utf-8") as f:
            json.dump(sections_layout, f, indent=2)

    def _select_poster_layout(self, state: PosterState, section_info: Dict, poster_layouts_file: Path):
        with open(poster_layouts_file, "r") as f:
            poster_layouts_data = json.load(f)
            ''' 这里的操作时通过section_info确定poster_layout_id '''
            print("start_select_poster_layout_id")
            poster_layout_id, sorted_areas = self._select_poster_layout_id(state, section_info, poster_layouts_data)
            poster_layout = poster_layouts_data[poster_layout_id]
            return poster_layout, sorted_areas

    def _select_poster_layout_id(self, state: PosterState, section_info: Dict, poster_layouts_data: Dict):
        #在我的视角中，海报看作16*12的网格，因为每张图片宽度原始尺寸应该都相同，我令所有图片宽度缩放至3个网格大小，按比例换算出宽度以及在网络中的面积，同时将文本占面积的大小用__caculate_text_area()得出，计算每一个section大概占比为多少，排序后，和poster_layouts_data中每一个排布方式做比较，最合适的选出来
        tables = state["tables"]
        figures = state["images"]

        sections = section_info["spatial_content_plan"]["sections"]
        section_areas = {}
        total_area = 0.0
        for section in sections:
            section_title = section["section_title"]
            if section_title.lower() == "title_author":
                title_font_size = 100
                visual_assets = section["visual_assets"]
                text_area = self._caculate_title_text_area(state, title_font_size)
                visual_assets_area = self._caculate_visual_area(visual_assets, tables, figures)#这里很可能没有素材，我的想法是后面补上默认图标
                section_areas[section_title] = visual_assets_area + text_area
                total_area += visual_assets_area + text_area
            else:
                text_font_size = 36
                section_content = section["text_content"]
                visual_assets = section["visual_assets"]
                visual_assets_area = self._caculate_visual_area(visual_assets, tables, figures)
                text_area = self._caculate_text_area(section_content, text_font_size)
                section_areas[section_title] = visual_assets_area + text_area
                total_area += visual_assets_area + text_area
        # 对面积排序
        for section_title, area in section_areas.items():
            total_area_ratio = area/total_area
            section_areas[section_title] = total_area_ratio#面积变为面积比
        sorted_areas = sorted(section_areas.items(), key=lambda x: x[1])

        layout_id = 0
        min_area_similarity = 10000
        for layout_data in poster_layouts_data:
            area_simlarity = 0.0
            rate = layout_data["rate"]
            for section_area_rate, poster_layout_rate in zip(sorted_areas, rate):
                area_simlarity += abs(section_area_rate[1] - poster_layout_rate)
            if area_simlarity < min_area_similarity:
                min_area_similarity = area_simlarity
                layout_id = layout_data["id"]
        print("best layout_id:", layout_id)
        return layout_id, sorted_areas

    def _caculate_title_text_area(self, state:PosterState, title_font_size=100) ->float:
        title_author = state["narrative_content"]["meta"]
        title_author_len = len(title_author["poster_title"]) + len(title_author["authors"])
        ratio = title_font_size/72
        text_area = (ratio*ratio)*title_author_len*(16*12)/(52*39)
        
        return text_area

    def _caculate_visual_area(self, visual_assets: Dict, tables: Dict, figures: Dict) -> float:
        table_area = 0.0
        figure_area = 0.0
        for visual_asset in visual_assets:
            try:
                id = visual_asset["visual_id"]
                id = id.split("_")
                if id[0] == "table":
                    table_id = id[1]
                    table = tables[table_id]
                    table_area += 3*3/table["aspect"]
                elif id[0] == "figure":
                    figure_id = id[1]
                    figure = figures[figure_id]
                    figure_area += 3*3/figure["aspect"]
            except:
                continue

        """ 计算图片占面积的大小 """
        total_area = table_area + figure_area
        return total_area
    
    def _caculate_text_area(self, text_content: Dict, text_font_size=36) -> float:
        """ 计算文本占面积的大小 """
        text_len = 0
        for line in text_content:
            text_len += len(line)
        ratio = text_font_size/72
        text_area = (ratio*ratio)*text_len*(16*12)/(52*39)
        total_area = text_area
        return total_area

    def _set_layout(self, section_info: Dict, poster_layout: Dict, sorted_area) -> Dict:
        sections_layout = []
        sections = section_info["spatial_content_plan"]["sections"]
        for id, info in enumerate(sorted_area):
            section_title = info[0]
            section_location = poster_layout["layout"][id]
            for section in sections:
                if(section["section_title"] == section_title):
                    section_layout = {
                        "section_title":section_title,
                        "section_content":section["text_content"],
                        "visual_assets":[item["visual_id"] for item in section["visual_assets"]],
                        "x":section_location[0],
                        "y":section_location[1],
                        "width":section_location[2] - section_location[0],
                        "height":section_location[3] - section_location[1],
                    }
                    sections_layout.append(section_layout)
        """ 设置海报布局 """
        return sections_layout
    
    def render_poster(self, state: PosterState, sections_layout: Dict):
        """ 渲染海报 """
        prs = Presentation()
        prs.slide_width = Inches(state["poster_width"])
        prs.slide_height = Inches(state["poster_height"])
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        ratio = 3.25  # 建议定义为常量，如 RATIO = 3.25
        FONT_SIZE_TITLE = Pt(50)
        FONT_SIZE_CONTENT = Pt(36) 
        for section_layout in sections_layout:
            x = section_layout["x"]
            y = section_layout["y"]
            width = section_layout["width"]
            height = section_layout["height"]
            
            # 1. 添加矩形容器
            container = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(x * ratio),
                Inches(y * ratio),
                Inches(width * ratio),
                Inches(height * ratio)
            )
            container.line.color.rgb = RGBColor(0, 0, 255)
            
            # ========== 核心修复：手动添加文本框 ==========
            # 检查是否有textbox，没有则手动添加
            if not hasattr(container, 'textbox') or container.textbox is None:
                # 在形状内部添加文本框（覆盖整个形状区域）
                textbox = slide.shapes.add_textbox(
                    Inches(x * ratio),  # 与形状x坐标一致
                    Inches(y * ratio),  # 与形状y坐标一致
                    Inches(width * ratio),  # 与形状宽度一致
                    Inches(height * ratio)  # 与形状高度一致
                )
                # 将文本框置于形状上方（视觉上）
                #textbox.z_order = container.z_order + 1
                # 文本框透明背景，不遮挡形状
                textbox.fill.solid()
                textbox.fill.fore_color.rgb = RGBColor(255, 255, 255)
                textbox.fill.fore_color.transparency = 1.0  # 完全透明
                textbox.line.fill.background()  # 无边框
            else:
                textbox = container.textbox
            # =============================================
            
            # 2. 配置文本框架
            tf = textbox.text_frame
            tf.clear()  # 清空默认文本
            tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP  # 垂直锚点（text_frame属性）
            tf.word_wrap = True  # 自动换行（新增，避免文本溢出）
            
            # 3. 设置标题段落
            title_para = tf.add_paragraph()  # 重新创建标题段落（避免默认段落问题）
            title_para.text = section_layout["section_title"]
            title_para.font.size = FONT_SIZE_TITLE
            title_para.font.bold = True
            title_para.alignment = PP_ALIGN.CENTER
            
            # 4. 添加内容段落
            for line in section_layout["section_content"]:
                content_para = tf.add_paragraph()
                content_para.text = line
                content_para.font.size = FONT_SIZE_CONTENT
                content_para.font.bold = False
                content_para.alignment = PP_ALIGN.LEFT
            
        prs.save(Path(state["output_dir"]) / "poster.pptx")
        return state

def renderer_node(state: PosterState) -> Dict[str, Any]:
    print("start_render_node")
    result = Renderer()(state)
    return {
        **state,
        "tokens": result["tokens"],
        "current_agent": result["current_agent"],
        "errors": result["errors"]
    }
