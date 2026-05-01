# 变量data文件夹中的每一个文件夹，每一个文件夹中应该都有paper.pdf和aff.png
import os
from pathlib import Path
DATA_FOLDER = "data"

for sub_folder in os.listdir(DATA_FOLDER):
    sub_folder_path = os.path.join(DATA_FOLDER, sub_folder)
    if os.path.isdir(sub_folder_path):
        paper_pdf = os.path.join(sub_folder_path, "paper.pdf")
        aff_png = os.path.join(sub_folder_path, "aff.png")
        if not os.path.exists(paper_pdf) or not os.path.exists(aff_png):
            print(f"Error: {sub_folder} is missing paper.pdf or aff.png")
            continue
        cmd = ["python", "-m", "src.workflow.pipeline"]
        cmd.append(f"--poster_width 48 --poster_height 36")
        cmd.append(f"--paper_path {paper_pdf}")
        cmd.append(f"--text_model qwen3.6-plus")
        cmd.append(f"--vision_model qwen3.6-plus")
        cmd.append(f"--aff_logo {aff_png}")
        print(" ".join(cmd))
        os.system(" ".join(cmd))
        exit(0)
'''
python -m src.workflow.pipeline 
  --poster_width 48 --poster_height 36 
  --paper_path ./data/Active_Geospatial_Search_for_Efficient_Tenant_Eviction_Outreach/paper.pdf 
  --text_model qwen3-max 
  --vision_model qwen3-vl-plus 
  --logo ./data/Active_Geospatial_Search_for_Efficient_Tenant_Eviction_Outreach/logo.png 
  --aff_logo ./data/Active_Geospatial_Search_for_Efficient_Tenant_Eviction_Outreach/aff.png
'''