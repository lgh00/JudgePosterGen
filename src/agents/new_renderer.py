import re
import qrcode
from pathlib import Path
from typing import Dict, Any, Optional
import json
import numpy as np

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
        section_info = self._preprocess_section_info(state, section_info)#预处理，将section_content改为提取内容
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
        sections_layout = self._set_layout(state, section_info, poster_layout, sorted_area)
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

    def _preprocess_section_info(self, state:PosterState, section_info: Dict):
        new_section_info = section_info.copy()
        sections = new_section_info["spatial_content_plan"]["sections"]
        title_author = state["narrative_content"]["meta"]
        for section in sections:
            if section["section_title"] == "title_author":
                section["text_content"] = [title_author["poster_title"], title_author["authors"]]
        state["story_board"] = new_section_info
        return new_section_info

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
                title_author_content = section["text_content"]
                visual_assets = section["visual_assets"]
                text_area = self._caculate_title_text_area(title_author_content, title_font_size)
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
        min_area_dissimilarity = 10000
        dissimilaritys = []
        for layout_data in poster_layouts_data:
            area_dissimilarity = 0.0
            rate = layout_data["rate"]
            for section_area_rate, poster_layout_rate in zip(sorted_areas, rate):
                area_dissimilarity += abs(section_area_rate[1] - poster_layout_rate)
            dissimilaritys.append(area_dissimilarity)
            if area_dissimilarity < min_area_dissimilarity:
                min_area_dissimilarity = area_dissimilarity
                layout_id = layout_data["id"]
        print("method1 layout_id:", layout_id)
        '''
        dissimilarity = np.array(dissimilaritys)
        min_indices = np.argpartition(dissimilarity, 20)[:20]
        layout_id = min_indices[0]
        print("min_indices:", min_indices)
        print("method2 layout_id:", layout_id)
        '''
        return layout_id, sorted_areas

    def _caculate_title_text_area(self, title_author_content: list, title_font_size=100) ->float:
        text_len = 0
        for line in title_author_content:
            text_len += len(line)
        ratio = title_font_size/72
        text_area = (ratio*ratio)*text_len*(16*12)/(52*39)
        return text_area

    def _caculate_visual_area(self, visual_assets: list, tables: Dict, figures: Dict) -> float:
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
    
    def _caculate_text_area(self, text_content: list, text_font_size=36) -> float:
        """ 计算文本占面积的大小 """
        text_len = 0
        for line in text_content:
            text_len += len(line)
        ratio = text_font_size/72
        text_area = (ratio*ratio)*text_len*(16*12)/(52*39)
        total_area = text_area
        return total_area

    def _set_layout(self, state: PosterState, section_info: Dict, poster_layout: Dict, sorted_area) -> Dict:
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
                        "x":section_location[0],
                        "y":section_location[1],
                        "width":section_location[2] - section_location[0] + 1,
                        "height":section_location[3] - section_location[1] + 1,
                    }   

                    '''获取视觉素材的布局信息'''
                    visuals_layout = []
                    for item in section["visual_assets"]:
                        visual_id = item["visual_id"]
                        visual_path, aspect = self._get_visual_path(visual_id, state)
                        if visual_path and Path(visual_path).exists():
                            visual_layout = {
                                "path":visual_path,
                                "x":section_location[0],
                                "y":section_location[1],
                                "width":3,
                                "height":3/aspect,
                                "aspect":aspect,
                            }
                            visuals_layout.append(visual_layout)

                    section_layout["visuals_layout"] = visuals_layout

            sections_layout.append(section_layout)
        """ 设置海报布局 """
        return sections_layout

    def _get_visual_path(self, visual_id: str, state: PosterState):
        """get path to visual asset"""
        images = state.get("images", {})
        tables = state.get("tables", {})
        vid = (visual_id or "").split('_')[-1]
        
        if visual_id.startswith("figure"):
            return images.get(vid, {}).get("path"), images.get(vid, {}).get("aspect")
        if visual_id.startswith("table"):
            return tables.get(vid, {}).get("path"), tables.get(vid, {}).get("aspect")
        
        return None, None

    def render_poster(self, state: PosterState, sections_layout: Dict):
        """ 渲染海报 """
        prs = Presentation()
        prs.slide_width = Inches(state["poster_width"])
        prs.slide_height = Inches(state["poster_height"])
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        ratio = 3.25  # 建议定义为常量，如 RATIO = 3.25
        FONT_SIZE_TITLE = Pt(50)

        for section_layout in sections_layout:
            if section_layout["section_title"] == "title_author":
                FONT_SIZE_CONTENT = Pt(100)
            else:
                FONT_SIZE_CONTENT = Pt(36)
            x = section_layout["x"]
            y = section_layout["y"]
            width = section_layout["width"]
            height = section_layout["height"]
            
            # 2.添加区块标题
            textbox = slide.shapes.add_textbox(
                Inches(x * ratio),  # 与形状x坐标一致
                Inches(y * ratio),  # 与形状y坐标一致
                Inches(width * ratio),  # 与形状宽度一致
                Inches(height * ratio)  # 与形状高度一致
            )
            textbox.fill.solid()
            textbox.fill.fore_color.rgb = RGBColor(255, 255, 255)
            textbox.fill.fore_color.transparency = 1.0  # 完全透明
            textbox.line.fill.background()  # 无边框

            tf = textbox.text_frame
            tf.clear()  # 清空默认文本
            tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP  # 垂直锚点（text_frame属性）
            tf.word_wrap = True  # 自动换行（新增，避免文本溢出）

            title_para = tf.add_paragraph()  # 重新创建标题段落（避免默认段落问题）
            title_para.text = section_layout["section_title"]
            title_para.font.size = FONT_SIZE_TITLE
            title_para.font.bold = True
            title_para.alignment = PP_ALIGN.CENTER
            '''设置子标题后，整个区块的起始位置和高度都应该变动，单位为格子'''
            sub_title_height = 1/ratio
            y += sub_title_height
            height -= sub_title_height

            # 3. 处理图片放置
            '''处理图片放置'''
            visual_assets_num = len(section_layout["visuals_layout"])
            if visual_assets_num == 0:
                pass
            elif visual_assets_num == 1:
                visual_asset = section_layout["visuals_layout"][0]
                visual_path = visual_asset["path"]
                visual_width = visual_asset["width"]
                visual_height = visual_asset["height"]
                if visual_width < width and visual_height < height:
                    strategy = "up" if (height-visual_height)*width > (width-visual_width)*height else "left"
                    if strategy == "up":
                        print(f"{section_layout['section_title']}的策略为up")
                        centered_left = Inches((x + (width - visual_width) / 2) * ratio)
                        centered_top = Inches(y * ratio)
                        final_width = Inches(visual_width * ratio)
                        final_height = Inches(visual_height * ratio)
                        slide.shapes.add_picture(visual_path, centered_left, centered_top, width=final_width, height=final_height)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        y += final_height
                        height -= final_height
                    elif strategy == "left":
                        print(f"{section_layout['section_title']}的策略为left")
                        centered_left = Inches(x * ratio)
                        centered_top = Inches((y + (height - visual_height) / 2) * ratio)
                        final_width = Inches(visual_width * ratio)
                        final_height = Inches(visual_height * ratio)
                        slide.shapes.add_picture(visual_path, centered_left, centered_top, width=final_width, height=final_height)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        x += final_width
                        width -= final_width
            elif visual_assets_num == 2:
                fine_to_place = True
                strategy = ""
                text_area = 0
                for visual_asset in section_layout["visuals_layout"]:
                    visual_width = visual_asset["width"]
                    visual_height = visual_asset["height"]
                    if visual_width > width or visual_height > height:
                        fine_to_place = False
                        break
                if fine_to_place:
                    visual_asset1 = section_layout["visuals_layout"][0]
                    visual_path1 = visual_asset1["path"]
                    visual_width1 = visual_asset1["width"]
                    visual_height1 = visual_asset1["height"]
                    visual_asset2 = section_layout["visuals_layout"][1]
                    visual_path2 = visual_asset2["path"]
                    visual_width2 = visual_asset2["width"]
                    visual_height2 = visual_asset2["height"]
                    if visual_height1+visual_height2 < height:
                        caculated_text_area = width * (height - visual_height1 - visual_height2)
                        if caculated_text_area > text_area:
                            text_area = caculated_text_area
                            strategy = "up1"
                    if visual_asset1["width"] + visual_asset2["width"] < width:
                        caculated_text_area = width * (height - max(visual_asset1["height"], visual_asset2["height"]))
                        if caculated_text_area > text_area:
                            text_area = caculated_text_area
                            strategy = "up2"
                    
                    if visual_width1+visual_width2 < width:
                        caculated_text_area = height * (width - visual_width1 - visual_width2)
                        if caculated_text_area > text_area:
                            text_area = caculated_text_area
                            strategy = "left1"
                    if visual_asset1["height"] + visual_asset2["height"] < height:
                        caculated_text_area = height * (width - max(visual_asset1["width"], visual_asset2["width"]))
                        if caculated_text_area > text_area:
                            text_area = caculated_text_area
                            strategy = "left2"
                    if strategy == "":
                        pass
                    elif strategy == "up1":
                        print(f"{section_layout['section_title']}的策略为{strategy}")
                        centered_left1 = Inches((x + (width - visual_width1) / 2) * ratio)
                        centered_top1 = Inches(y * ratio)
                        final_width1 = Inches(visual_width1 * ratio)
                        final_height1 = Inches(visual_height1 * ratio)
                        slide.shapes.add_picture(visual_path1, centered_left1, centered_top1, width=final_width1, height=final_height1)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        y += visual_height1
                        height -= visual_height1
                        centered_left2 = Inches((x + (width - visual_width2) / 2) * ratio)
                        centered_top2 = Inches(y * ratio)
                        final_width2 = Inches(visual_width2 * ratio)
                        final_height2 = Inches(visual_height2 * ratio)
                        slide.shapes.add_picture(visual_path2, centered_left2, centered_top2, width=final_width2, height=final_height2)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        y += visual_height2
                        height -= visual_height2
                    elif strategy == "up2":
                        print(f"{section_layout['section_title']}的策略为{strategy}")
                        centered_left1 = Inches((x + (width/2 - visual_width1)/2) * ratio)
                        centered_top1 = Inches(y * ratio)
                        final_width1 = Inches(visual_width1 * ratio)
                        final_height1 = Inches(visual_height1 * ratio)
                        slide.shapes.add_picture(visual_path1, centered_left1, centered_top1, width=final_width1, height=final_height1)
                        centered_left2 = Inches((x + width/2 + (width/2 - visual_width2)/2) * ratio)
                        centered_top2 = Inches(y * ratio)
                        final_width2 = Inches(visual_width2 * ratio)
                        final_height2 = Inches(visual_height2 * ratio)
                        slide.shapes.add_picture(visual_path2, centered_left2, centered_top2, width=final_width2, height=final_height2)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        y += max(visual_height1, visual_height2)
                        height -= max(visual_height1, visual_height2)
                    elif strategy == "left1":
                        print(f"{section_layout['section_title']}的策略为{strategy}")
                        centered_left1 = Inches(x * ratio)
                        centered_top1 = Inches((y + (height - visual_height1) / 2) * ratio)
                        final_width1 = Inches(visual_width1 * ratio)
                        final_height1 = Inches(visual_height1 * ratio)
                        slide.shapes.add_picture(visual_path1, centered_left1, centered_top1, width=final_width1, height=final_height1)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        x += visual_width1
                        width -= visual_width1
                        centered_left2 = Inches(x * ratio)
                        centered_top2 = Inches((y + (height - visual_height2) / 2) * ratio)
                        final_width2 = Inches(visual_width2 * ratio)
                        final_height2 = Inches(visual_height2 * ratio)
                        slide.shapes.add_picture(visual_path2, centered_left2, centered_top2, width=final_width2, height=final_height2)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        x += visual_width2
                        width -= visual_width2
                    elif strategy == "left2":
                        print(f"{section_layout['section_title']}的策略为{strategy}")
                        centered_left1 = Inches(x * ratio)
                        centered_top1 = Inches((y + (height/2 - visual_height1)/2) * ratio)
                        final_width1 = Inches(visual_width1 * ratio)
                        final_height1 = Inches(visual_height1 * ratio)
                        slide.shapes.add_picture(visual_path1, centered_left1, centered_top1, width=final_width1, height=final_height1)
                        centered_left2 = Inches(x * ratio)
                        centered_top2 = Inches((y + height/2 + (height/2 - visual_height2)/2) * ratio)
                        final_width2 = Inches(visual_width2 * ratio)
                        final_height2 = Inches(visual_height2 * ratio)
                        slide.shapes.add_picture(visual_path2, centered_left2, centered_top2, width=final_width2, height=final_height2)
                        '''设置图片后，整个区块的起始位置和高度都应该变动，单位为格子'''
                        x += max(visual_width1, visual_width2)
                        width -= max(visual_width1, visual_width2)
                
            # 在形状内部添加文本框（覆盖整个形状区域）
            textbox = slide.shapes.add_textbox(
                Inches(x * ratio),  # 与形状x坐标一致
                Inches(y * ratio),  # 与形状y坐标一致
                Inches(width * ratio),  # 与形状宽度一致
                Inches(height * ratio)  # 与形状高度一致
            )
            # 将文本框置于形状上方（视觉上）
            # 文本框透明背景，不遮挡形状
            textbox.fill.solid()
            textbox.fill.fore_color.rgb = RGBColor(255, 255, 255)
            textbox.fill.fore_color.transparency = 1.0  # 完全透明
            textbox.line.fill.background()  # 无边框

            # =============================================
            # 4. 配置文本框架
            tf = textbox.text_frame
            tf.clear()  # 清空默认文本
            tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP  # 垂直锚点（text_frame属性）
            tf.word_wrap = True  # 自动换行（新增，避免文本溢出）
            
            
            # 5. 添加内容段落
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

for i in range(10):
    if i == 0:
        print
    else:
        print(i)
    print("---")