import os
import pdb
import json
import base64
from pathlib import Path
from typing import Dict, Any, Tuple
from jinja2 import Template

from src.state.poster_state import PosterState
from utils.langgraph_utils import LangGraphAgent, extract_json, load_prompt
from utils.src.logging_utils import log_agent_info, log_agent_success, log_agent_error, log_agent_warning
from src.config.poster_config import load_config

class ScoreAgent:
    def __init__(self):
        self.name = "score_agent"
        self.validation_config = load_config()["validation"]
        self.score_prompt = load_prompt("config/prompts/score_rendered_poster.txt")
    
    def __call__(self, state: PosterState) -> PosterState:
        log_agent_info(self.name, "starting scoring poster")
        try:
            # 提取当前section对应的布局总数
            with open(Path(state["resource_dir"]) / "poster_layouts/new_poster_layouts.json", 'r', encoding='utf-8') as f:
                poster_layouts = json.load(f)
                poster_layouts = poster_layouts[str(state["section_number"])]
            poster_score = {}
            for poster_layout in poster_layouts:
                poster_path = Path(state["output_dir"]) / f"poster_{poster_layout['id']}.png"
                result = self._score_poster(poster_path, state)
                poster_score[str(poster_layout['id'])] = {"special_score": result}
                final_score = 0
                for score in result.values():
                    final_score += score
                poster_score[str(poster_layout['id'])]["final_score"] = final_score / len(result)
            log_agent_info(self.name, "starting selecting best poster")
            max_score = 0
            max_score_id = ""
            for poster_id, score in poster_score.items():
                if max_score < score["final_score"]:
                    max_score = score["final_score"]
                    max_score_id = poster_id
            os.rename(Path(state["output_dir"]) / f"poster_{max_score_id}.png", Path(state["output_dir"]) / "best_poster.png")
            self._save_score(state, poster_score[max_score_id])
            log_agent_success(self.name, f"successfully select best poster poster_{max_score_id}")
        except Exception as e:
            log_agent_error(self.name, f"failed: {e}")
            state["errors"].append(f"{self.name}: {e}")
        return state

    def _score_poster(self, poster_path: Path, state: PosterState):
        log_agent_info(self.name, f"scoring poster {Path(poster_path).name}")
        max_attempts = self.validation_config["max_llm_attempts"]
        for attempt in range(max_attempts):
            try:
                with open(poster_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
                    
                agent = LangGraphAgent(
                    "poster scoring expert",
                    state["vision_model"],
                    state,
                    "score_agent"
                )
                with open("config/prompts/score_render_poster_standards.json", 'r', encoding='utf-8') as f:
                    score_standard = json.load(f)
                raw_text = state["raw_text"]
                template_data = {
                    "raw_text": raw_text,
                    "score_standard": json.dumps(score_standard, indent=2)
                }
                score_prompt = Template(self.score_prompt).render(**template_data)
                ###检验
                messages = [
                        {"type": "text", "text": score_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_data}"}}
                ]
                
                response = agent.step(json.dumps(messages))
                with open(Path(state["output_dir"]) / "model_reply_score_poster.txt", "w", encoding='utf-8') as f:
                    f.write(response.content)
                    print("successfully write model's reply of scoring poster")
                result = extract_json(response.content)
                if self._validate_score(result, score_standard):
                    log_agent_success(self.name, f"successfully scored poster {Path(poster_path).name}")
                    return result
                else:
                    log_agent_warning(self.name, f"attempt {attempt + 1}: validation failed, retrying")
                
            except Exception as e:
                log_agent_warning(self.name, f"scoring poster attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    raise ValueError("failed to score poster after multiple attempts")
        raise ValueError("failed to score poster")

    def _validate_score(self, result: Dict, score_standard: Dict) -> bool:
        """validate score result"""
        for key in score_standard.keys():
            if key not in result:
                log_agent_warning(self.name, f"missing key {key}")
                return False
        return True

    def _save_score(self, state: PosterState, poster_score: Dict):
        with open(Path(state["output_dir"]) / f"content/best_poster_score.json", "w", encoding='utf-8') as f:
            json.dump(poster_score, f, indent=2)
        log_agent_success(self.name, f"successfully save best poster score")
def score_agent_node(state: PosterState) -> PosterState:
    return ScoreAgent()(state)

