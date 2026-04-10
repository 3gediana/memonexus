import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from src.tools.memory_tools import get_db
from src.system.fingerprint import get_utc_now

def seed_space():
    conn = get_db()
    cursor = conn.cursor()
    
    space_items = [
        "考研常识：北大计科近年复试分数线通常在380分以上，竞争极其激烈。专业课考408(数据结构、计算机组成原理、操作系统、计算机网络)或自命题部分。",
        "咖啡因摄入建议：瑞幸美式含有较多咖啡因，提神效果因人而异，但空腹喝或长期大量饮用容易导致胃酸过多引发胃痛或反酸。",
        "记忆法知识：艾宾浩斯记忆法建议的最佳复习节点为：学完后20分钟、1小时、8-9小时、1天、2天、4天、7天、15天。",
        "心理疏导建议：考研备考中后期的焦虑情绪属于普遍的正常心理现象。对付焦虑最好的解药是立即行动，或通过适量中等强度的运动（如慢跑3公里）来释放多巴胺。",
        "考研规划常识：冲刺阶段（10-12月）重心应当转移到真题研究和政治背诵上，同时一定要按真实的考试时间（上午数学下午英语等）进行全真模考。"
    ]
    
    now = get_utc_now()
    count = 0
    for item in space_items:
        # Check if already exists
        exists = cursor.execute("SELECT 1 FROM memory_space WHERE content = ?", (item,)).fetchone()
        if not exists:
            cursor.execute('''
                INSERT INTO memory_space (content, created_at, updated_at, source)
                VALUES (?, ?, ?, ?)
            ''', (item, now, now, "system_seeder"))
            count += 1
            
    conn.commit()
    conn.close()
    print(f"成功注入 {count} 条公共知识到 memory_space 中。")

if __name__ == "__main__":
    seed_space()
