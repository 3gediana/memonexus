import os
import sys
import time
import json
from datetime import datetime, timedelta
import random

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from src.tools.memory_tools import get_db
from src.system.fingerprint import generate_fingerprint

# 模拟开始时间：2026-01-01
start_date = datetime(2026, 1, 1, 8, 0, 0)

# 定义预设数据 (日期偏移天数, Key, 源文本/事实, summary_item)
DATA_RECORDS = [
    # 基础信息
    (0, "study", "小林，大三学生，武汉普通211大学计算机专业", "基本信息：小林(大三)，武汉211计算机专业"),
    (0, "study", "考研目标：北京大学计算机科学与技术专业", "考研目标：北大计科"),
    (0, "relationship", "大学室友小王也准备考研，目标清华软件工程", "室友：小王，目标清华软工"),
    (1, "relationship", "女朋友小雅，在同一城市", "女友：小雅，同城"),
    
    # 学科基础与进度
    (3, "study", "高数基础一般，大一期末72分，需从头打基础", "高数基础：薄弱(期末72分)"),
    (3, "study", "英语四级550分六级489分，阅读理解较弱", "英语基础：四级550/六级489，阅读弱"),
    (4, "study", "专业课包含数据结构和算法，有ACM比赛经验，较擅长", "专业课优势：有ACM经验，擅长算法与数据结构"),
    (5, "study", "教材：张宇高数十八讲, 李永乐线性代数, 朱伟恋练有词", "使用教材：张宇十八讲、李永乐线代、恋练有词"),
    (6, "schedule", "复习规划：1-3月基础, 4-6月强化, 7-9月真题, 10-12月冲刺", "宏观规划：1-3月基础/4-6月强化/7-9月真题/10-12冲刺"),
    (7, "schedule", "日常作息：7点起，8点到图书馆，11点回宿舍", "日常作息：7:00起 - 23:00回"),
    (7, "preference", "喜欢在图书馆三楼靠窗位置学习", "偏好地点：图书馆三楼靠窗"),
    
    # 一月进展
    (15, "study", "高数第一章极限复习完，概念较好但计算易粗心", "进度：一月中旬完成高数极限，计算粗心"),
    (17, "study", "英语单词背了200个，使用艾宾浩斯法", "进度：英语单词开始背诵(艾宾浩斯)"),
    (20, "emotion", "失眠，担心如果考不上北大怎么办，压力大", "情绪：1月下旬因焦虑北大难度而失眠"),
    (21, "relationship", "跟小王吃火锅倾诉压力，感觉好多了", "互动：与小王聚餐缓解焦虑"),
    (30, "study", "一月底总结：高数推进到第三章，英语背了2000个单词", "里程碑：1月底完成高数第三章，单词2000"),
    (30, "preference", "喜欢喝瑞幸美式咖啡提神", "偏好饮品：瑞幸美式"),
    
    # 二月进展
    (40, "study", "高数第四章不定积分换元法和分部积分需大量练习", "进度：2月上旬攻克不定积分(难点)"),
    (45, "emotion", "第一套数学模拟题78分，基础题易错，受打击", "事件：首次模拟考78分(受挫)"),
    (46, "relationship", "情人节小雅表达了对考研的全力支持", "互动：情人节获女友全力支持"),
    (50, "study", "开始线性代数复习，从行列式开始(李永乐)", "进度：2月下旬开始线代(行列式)"),
    (53, "health", "长期久坐导致头疼", "健康：久坐导致头疼"),
    (54, "health", "开始每周运动：周二/四跑步3公里，周末篮球", "健康：增加运动(每周跑2次+1次篮球)"),
    (59, "study", "第二次数学模拟考92分(进步14分)", "里程碑：2月底模考92分(进步明显)"),
    
    # 三月进展
    (65, "study", "高数第五章定积分，面积体积应用是重点", "进度：3月上旬复习定积分应用"),
    (66, "emotion", "小王模考105分，感到有竞争压力", "情绪：因小王模考高分产生同辈压力"),
    (75, "study", "第三次数学模考101分，线代特征值和概率论是弱点", "进度：3月中旬模考101分，线代/概率论薄弱"),
    (79, "study", "英语阅读正确率达到65%，开始背高分范文", "进度：英语阅读正确率65%，启动作文"),
    (81, "relationship", "小王近期压力大失眠，周末一起打篮球解压", "互动：陪小王打球缓解其压力"),
    (86, "study", "第四次模考最高分112分，由于线代发挥好", "里程碑：3月底模考达112分(峰值)"),
    (88, "study", "提前开始政治，复习马原基础概念", "进度：政治提前启动，看马原基础"),
    
    # 四月冲刺与真题
    (90, "study", "开始做2020年数学真题，得分115", "进度：3月底开始真题，首套115分"),
    (93, "study", "发现概率论是最大弱点，花2天专项突破条件概率和贝叶斯", "进度：专项突破概率论重点"),
    (100, "study", "2022年数学真题125分，填空全对", "里程碑：4月上旬真题达125分"),
    (101, "health", "调整作息保证8小时睡眠，状态改善", "健康：保证8小时睡眠，精力恢复"),
    (104, "study", "2023年数学真题128分，概率论不再丢分", "里程碑：4月中旬真题128分(概率论短板补齐)"),
    (105, "schedule", "目前安排：上午数学2h+专业课1h，下午英语2h+专1h，晚政治1h+错题1h", "最新规划：三段式复习(数/英/政按时段)"),
    (106, "study", "建立了各科错题本，高数错题最多", "进度：建立错题本系统"),
    (110, "emotion", "随着后期临近，感到焦虑觉得书读不完", "情绪：4月中下旬产生“书读不完”的焦虑"),
    (112, "health", "吃饭不规律导致胃不舒服（特别是不吃早餐）", "健康：因饮食不规律引发胃痛"),
    (115, "study", "第五次数学全真模拟达130分", "里程碑：4月下旬模考稳定在130分以上"),
    (116, "study", "现阶段各科目标：数学130+ 英语75+ 政治70+ 专业课120+", "目标：总分395分冲刺"),
]


def fast_seed_memories():
    conn = get_db()
    cursor = conn.cursor()
    
    print(f"快速注入考研记忆 ({len(DATA_RECORDS)}条)...")
    t0 = time.time()
    
    stored = []
    
    for days_offset, key, memory_text, summary_item in DATA_RECORDS:
        sim_date = start_date + timedelta(days=days_offset)
        # 加点随机时分秒
        sim_date = sim_date.replace(hour=random.randint(8, 22), minute=random.randint(0, 59))
        ts_str = sim_date.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        
        fp = generate_fingerprint(memory_text)
        tag = memory_text[:15] + "..." if len(memory_text) > 15 else memory_text
        
        # 插入记忆
        cursor.execute('''
            INSERT OR IGNORE INTO memory 
            (fingerprint, key, memory, tag, summary_item, created_at, updated_at, base_score) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fp, key, memory_text, tag, summary_item, ts_str, ts_str, 0.8))
        
        stored.append({
            "fp": fp,
            "key": key,
            "ts": ts_str,
            "day": days_offset
        })

    # 构建关系网 (edges)
    # 取相近天数、相同key的建立边
    edges_count = 0
    for i in range(len(stored)):
        for j in range(i + 1, len(stored)):
            m1 = stored[i]
            m2 = stored[j]
            
            # 规则1：同Key 且 时间相近（7天内）建立强关联
            strong_edge = False
            if m1["key"] == m2["key"] and abs(m1["day"] - m2["day"]) <= 7:
                strong_edge = True
                
            # 规则2：不同Key但有关联（如久坐-头疼 vs 打球-解压）
            cross_edge = False
            if m1["key"] in ("emotion", "health") and m2["key"] in ("study", "schedule"):
                if abs(m1["day"] - m2["day"]) <= 3:
                     cross_edge = True

            if strong_edge or cross_edge:
                weight = 0.8 if strong_edge else 0.5
                cursor.execute('''
                    INSERT OR IGNORE INTO edges 
                    (from_fingerprint, to_fingerprint, strength, reason, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (m1["fp"], m2["fp"], weight, "Seeded relationship", ts_str, ts_str))
                edges_count += 1
                
    conn.commit()
    
    # 强制更新summary.json文件
    from src.tools.key_tools import get_current_keys_dir
    keys_dir = get_current_keys_dir()
    for key in set([m["key"] for m in stored]):
        key_dir = os.path.join(keys_dir, key)
        os.makedirs(key_dir, exist_ok=True)
        summary_file = os.path.join(key_dir, "summary.json")
        items = [s for d, k, t, s in DATA_RECORDS if k == key]
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": "\\n".join(items),
                "updated_at": ts_str
            }, f, ensure_ascii=False, indent=2)

    total_mem = cursor.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    total_edges = cursor.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    conn.close()

    elapsed = time.time() - t0
    print(f"\\n快速注入完成！耗时: {elapsed:.2f} 秒")
    print(f"总记忆数: {total_mem}")
    print(f"总关联边: {total_edges}")
    print("现在可以录制 Demo 视频了！")

if __name__ == "__main__":
    fast_seed_memories()
