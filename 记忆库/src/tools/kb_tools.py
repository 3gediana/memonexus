"""知识库工具定义和执行

重构版：融合 update-index 流程，一键自动索引
- 自动将中文文件名翻译为英文（Ollama 本地模型）
- 扫描资料目录找未索引文件
- 提取文本 → 智能分块 → 关键词索引 → 向量索引
- 返回结构化结果
"""

import subprocess
import json
import sqlite3
import os
import re
import hashlib
import logging
import requests
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

KB_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent / "\u77e5\u8bc6\u5e93"
)

MATERIAL_DIR = os.path.join(KB_DIR, "资料")
DB_PATH = os.path.join(KB_DIR, ".metadata", "knowledge-base.db")
INDEX_JSON = os.path.join(KB_DIR, ".metadata", "file-index.json")
CHUNKS_DIR = os.path.join(KB_DIR, ".chunks")

SUPPORTED_EXT = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".txt",
    ".md",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
}

OLLAMA_API = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5"

KB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "kb_index",
            "description": "一键索引资料库：自动翻译中文文件名 → 扫描未索引文件 → 提取文本/分块/建索引 → 返回结果。无需传参数，调用即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：指定文件/目录路径列表。不传则自动扫描资料目录",
                    },
                    "force_reindex": {
                        "type": "boolean",
                        "description": "是否强制重新索引已索引的文件，默认false",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_search",
            "description": "混合搜索知识库（关键词+语义），返回最相关的文本块",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询文本"},
                    "topK": {"type": "integer", "description": "返回结果数量，默认5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_sans_search",
            "description": "【sans模式专用】搜索知识库并用本地AI总结。当用户输入sans(问题)时必须使用此工具！输出400-600字详细总结。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询文本"},
                    "summaryInstruction": {"type": "string", "description": "总结指令", "default": "请简要概括这段内容"},
                    "topK": {"type": "integer", "description": "返回结果数量，默认10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_get_chunk",
            "description": "获取单个文本块的完整内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "chunkId": {
                        "type": "string",
                        "description": "块ID，格式：指纹-序号",
                    }
                },
                "required": ["chunkId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_get_document",
            "description": "获取文档信息及所有文本块",
            "parameters": {
                "type": "object",
                "properties": {
                    "fingerprint": {
                        "type": "string",
                        "description": "文件指纹（16位MD5）",
                    }
                },
                "required": ["fingerprint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_list_indexed",
            "description": "列出所有已索引的文件",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_get_stats",
            "description": "获取知识库统计信息",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kb_remove_file",
            "description": "从知识库中删除指定文件的索引",
            "parameters": {
                "type": "object",
                "properties": {
                    "fingerprint": {
                        "type": "string",
                        "description": "文件指纹（16位MD5）",
                    }
                },
                "required": ["fingerprint"],
            },
        },
    },
]


def execute_kb_tool(tool_name: str, args: dict) -> dict:
    """执行知识库工具"""
    try:
        if tool_name == "kb_index":
            return _kb_index(args.get("paths"), args.get("force_reindex", False))
        elif tool_name == "kb_search":
            return _kb_search(args.get("query"), args.get("topK", 5))
        elif tool_name == "kb_sans_search":
            return _kb_sans_search(
                args.get("query"), args.get("summaryInstruction"), args.get("topK", 10)
            )
        elif tool_name == "kb_get_chunk":
            return _kb_get_chunk(args.get("chunkId"))
        elif tool_name == "kb_get_document":
            return _kb_get_document(args.get("fingerprint"))
        elif tool_name == "kb_list_indexed":
            return _kb_list_indexed()
        elif tool_name == "kb_get_stats":
            return _kb_get_stats()
        elif tool_name == "kb_remove_file":
            return _kb_remove_file(args.get("fingerprint"))
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _ollama_translate(text: str) -> str:
    """用 Ollama 本地模型翻译中文为英文"""
    try:
        resp = requests.post(
            OLLAMA_API,
            json={
                "model": OLLAMA_MODEL,
                "prompt": f"将以下中文翻译为英文，只返回翻译结果，不要任何解释：{text}",
                "stream": False,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning(f"Ollama 翻译失败: {e}")
    return ""


def _translate_filename(chinese_name: str) -> str:
    """将中文文件名翻译为英文"""
    ext_match = re.match(r"^(.+)\.([^.]+)$", chinese_name)
    if not ext_match:
        return chinese_name

    name = ext_match.group(1)
    ext = ext_match.group(2)

    translated = _ollama_translate(name)
    if not translated:
        return None

    safe_name = re.sub(r"[^a-zA-Z0-9\s_-]", "", translated)
    safe_name = re.sub(r"\s+", "-", safe_name).lower()
    if not safe_name:
        return None
    return f"{safe_name}.{ext}"


def _rename_chinese_files(directory: str) -> list:
    """扫描目录，将中文文件名翻译为英文并重命名"""
    renamed = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            d
            for d in dirs
            if d not in {"node_modules", ".scripts", ".git", "dist", ".vscode"}
        ]
        for fname in files:
            if not re.search(r"[\u4e00-\u9fff]", fname):
                continue
            fpath = os.path.join(root, fname)
            new_name = _translate_filename(fname)
            if not new_name or new_name == fname:
                continue
            new_path = os.path.join(root, new_name)
            if os.path.exists(new_path):
                logger.info(f"跳过重命名（目标已存在）: {fname} -> {new_name}")
                continue
            os.rename(fpath, new_path)
            renamed.append(f"{fname} -> {new_name}")
            logger.info(f"重命名: {fname} -> {new_name}")
    return renamed


def _scan_files(directory: str) -> list:
    """扫描目录获取所有支持的文件路径"""
    files = []
    for root, dirs, fnames in os.walk(directory):
        dirs[:] = [
            d
            for d in dirs
            if d not in {"node_modules", ".scripts", ".git", "dist", ".vscode"}
        ]
        for fname in fnames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_EXT:
                files.append(os.path.join(root, fname))
    return files


def _get_indexed_paths() -> set:
    """从 SQLite 获取已索引的文件路径集合"""
    if not os.path.exists(DB_PATH):
        return set()
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT path FROM files WHERE status = 'indexed'"
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _init_db():
    """初始化数据库表"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            fingerprint TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            size INTEGER,
            mtime TEXT,
            status TEXT DEFAULT 'pending',
            indexed_at TEXT,
            chunks_count INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_index (
            word TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (word, chunk_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_keyword_chunk ON keyword_index(chunk_id)"
    )
    conn.commit()
    return conn


def _kb_index(paths: list = None, force: bool = False) -> dict:
    """一键索引：自动翻译中文文件名 → 扫描未索引 → 提取/分块/建索引

    Returns:
        {
            "success": true,
            "renamed": ["中文名.pdf -> english-name.pdf", ...],
            "indexed": [
                {"file": "english-name.pdf", "fingerprint": "abc123", "chunks": 15},
                ...
            ],
            "skipped": 3,
            "errors": []
        }
    """
    from src.tools.kb_extractor import extract_text
    from src.tools.kb_chunker import split as chunk_split
    from src.tools.kb_keyword import KeywordIndexer
    from src.tools.kb_vector import VectorIndexer

    renamed = []
    indexed = []
    errors = []
    skipped = 0

    # 步骤 1: 翻译中文文件名
    scan_dir = MATERIAL_DIR if (not paths or not paths) else None
    if scan_dir and os.path.isdir(scan_dir):
        renamed = _rename_chinese_files(scan_dir)

    # 步骤 2: 确定要索引的文件
    if paths:
        file_list = []
        for p in paths:
            if os.path.isdir(p):
                file_list.extend(_scan_files(p))
            elif os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in SUPPORTED_EXT:
                    file_list.append(p)
    else:
        file_list = _scan_files(scan_dir) if scan_dir else []

    indexed_paths = _get_indexed_paths()
    pending = [f for f in file_list if f not in indexed_paths or force]
    skipped = len(file_list) - len(pending)

    if not pending:
        return {
            "success": True,
            "message": "所有文件已索引完毕",
            "renamed": renamed,
            "indexed": [],
            "skipped": skipped,
            "errors": [],
        }

    # 步骤 3: 初始化模块
    conn = _init_db()
    keyword_indexer = KeywordIndexer(conn)
    vector_indexer = VectorIndexer()
    vector_indexer.restore_from_backup()

    # 步骤 4: 逐个索引
    for file_path in pending:
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            fingerprint = hashlib.md5(content).hexdigest()[:16]
            stat = os.stat(file_path)

            text = extract_text(file_path)
            if not text.strip():
                errors.append(
                    {"file": os.path.basename(file_path), "error": "提取文本为空"}
                )
                continue

            chunks = chunk_split(text, fingerprint)
            chunk_dicts = [{"id": c.id, "text": c.text} for c in chunks]

            keyword_indexer.add_batch(chunk_dicts)
            vector_indexer.add_batch(chunk_dicts)
            vector_indexer.save(fingerprint)

            conn.execute(
                "INSERT OR REPLACE INTO files (fingerprint, path, size, mtime, status, indexed_at, chunks_count) VALUES (?, ?, ?, ?, 'indexed', datetime('now'), ?)",
                (fingerprint, file_path, stat.st_size, stat.st_mtime, len(chunks)),
            )
            conn.commit()

            chunk_dir = os.path.join(CHUNKS_DIR, fingerprint[:2])
            os.makedirs(chunk_dir, exist_ok=True)
            with open(
                os.path.join(chunk_dir, f"{fingerprint}.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(
                    {
                        "fingerprint": fingerprint,
                        "totalChunks": len(chunks),
                        "createdAt": datetime.now().isoformat(),
                        "chunks": [
                            {
                                "id": c.id,
                                "text": c.text,
                                "index": c.index,
                                "startPos": c.start_pos,
                                "endPos": c.end_pos,
                                "blockType": c.block_type,
                                "headingLevel": c.heading_level,
                                "headingText": c.heading_text,
                            }
                            for c in chunks
                        ],
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            index_data = {}
            if os.path.exists(INDEX_JSON):
                with open(INDEX_JSON, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            index_data[fingerprint] = {
                "fingerprint": fingerprint,
                "path": file_path,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "status": "indexed",
                "indexedAt": datetime.now().isoformat(),
                "chunksCount": len(chunks),
            }
            with open(INDEX_JSON, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

            indexed.append(
                {
                    "file": os.path.basename(file_path),
                    "fingerprint": fingerprint,
                    "chunks": len(chunks),
                    "text_length": len(text),
                }
            )
        except Exception as e:
            errors.append({"file": os.path.basename(file_path), "error": str(e)})

    keyword_indexer.flush()
    conn.close()

    return {
        "success": True,
        "renamed": renamed,
        "indexed": indexed,
        "skipped": skipped,
        "errors": errors,
    }


def _kb_search(query: str, topK: int) -> dict:
    """混合搜索：关键词 + 语义"""
    from src.tools.kb_keyword import KeywordIndexer, extract_keywords
    from src.tools.kb_vector import VectorIndexer

    if not os.path.exists(DB_PATH):
        return {"success": True, "results": [], "count": 0}

    conn = sqlite3.connect(DB_PATH)
    keyword_indexer = KeywordIndexer(conn)
    kw_ids = keyword_indexer.search(query)
    conn.close()

    vector_indexer = VectorIndexer()
    vector_indexer.restore_from_backup()
    vec_results = (
        vector_indexer.search(query, topK * 2) if vector_indexer.is_ready() else []
    )

    merged = {}
    for r in vec_results:
        merged[r["chunkId"]] = r["score"]
    for cid in kw_ids:
        merged[cid] = merged.get(cid, 0) + 0.7

    sorted_ids = sorted(merged.keys(), key=lambda x: merged[x], reverse=True)[:topK]

    results = []
    for chunk_id in sorted_ids:
        parts = chunk_id.rsplit("-", 1)
        if len(parts) != 2:
            continue
        fingerprint = parts[0]
        chunk_file = os.path.join(CHUNKS_DIR, fingerprint[:2], f"{fingerprint}.json")
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for chunk in data.get("chunks", []):
                if chunk["id"] == chunk_id:
                    results.append(
                        {
                            "chunk_id": chunk_id,
                            "text": chunk.get("text", ""),
                            "fingerprint": fingerprint,
                            "score": round(merged[chunk_id], 3),
                        }
                    )
                    break
        except (FileNotFoundError, json.JSONDecodeError):
            continue

    return {"success": True, "results": results, "count": len(results)}


def _kb_sans_search(query: str, instruction: str, topK: int) -> dict:
    """搜索 + AI 总结"""
    search_result = _kb_search(query, topK)
    if not search_result["success"] or not search_result["results"]:
        return {"success": True, "summary": "未找到相关信息", "hasData": False}

    context = "\n---\n".join(r["text"][:500] for r in search_result["results"])

    try:
        resp = requests.post(
            OLLAMA_API,
            json={
                "model": OLLAMA_MODEL,
                "prompt": f"根据以下资料，{instruction}\n\n资料：\n{context[:3000]}",
                "stream": False,
            },
            timeout=60,
        )
        summary = resp.json().get("response", "总结失败")
        return {
            "success": True,
            "summary": summary,
            "hasData": True,
            "aiSummarized": True,
            "chunkCount": len(search_result["results"]),
        }
    except Exception as e:
        return {
            "success": True,
            "summary": f"AI 总结失败: {e}，返回原始搜索结果",
            "rawResult": search_result["results"],
            "hasData": True,
            "aiSummarized": False,
        }


def _kb_list_indexed() -> dict:
    """列出已索引文件"""
    if not os.path.exists(DB_PATH):
        return {"success": True, "files": [], "count": 0}
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT fingerprint, path, size, mtime, status, indexed_at, chunks_count FROM files WHERE status = 'indexed'"
    ).fetchall()
    conn.close()
    files = [
        {
            "fingerprint": r[0],
            "path": r[1],
            "name": os.path.basename(r[1]) or r[0],
            "status": r[4],
            "chunks_count": r[6] or 0,
            "size": r[2] or 0,
        }
        for r in rows
    ]
    return {"success": True, "files": files, "count": len(files)}


def _kb_get_stats() -> dict:
    """获取统计信息"""
    if not os.path.exists(DB_PATH):
        return {"success": True, "documents": 0, "chunks": 0}
    conn = sqlite3.connect(DB_PATH)
    doc_count = conn.execute(
        "SELECT COUNT(*) FROM files WHERE status = 'indexed'"
    ).fetchone()[0]
    chunk_count = conn.execute(
        "SELECT COALESCE(SUM(chunks_count), 0) FROM files WHERE status = 'indexed'"
    ).fetchone()[0]
    conn.close()
    return {"success": True, "documents": doc_count, "chunks": chunk_count}


def _kb_get_chunk(chunk_id: str) -> dict:
    """获取单个文本块"""
    parts = chunk_id.rsplit("-", 1)
    if len(parts) != 2:
        return {"success": False, "error": "chunk_id 格式错误"}
    fingerprint = parts[0]
    chunk_file = os.path.join(CHUNKS_DIR, fingerprint[:2], f"{fingerprint}.json")
    try:
        with open(chunk_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for chunk in data.get("chunks", []):
            if chunk["id"] == chunk_id:
                return {"success": True, "chunk": chunk, "document": data}
        return {"success": False, "error": "chunk 不存在"}
    except FileNotFoundError:
        return {"success": False, "error": "未找到该 chunk"}


def _kb_get_document(fingerprint: str) -> dict:
    """获取文档所有块"""
    chunk_file = os.path.join(CHUNKS_DIR, fingerprint[:2], f"{fingerprint}.json")
    try:
        with open(chunk_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "success": True,
            "fingerprint": fingerprint,
            "document": data,
            "chunks": data.get("chunks", []),
            "count": len(data.get("chunks", [])),
        }
    except FileNotFoundError:
        return {"success": False, "error": "未找到该文档"}


def _kb_remove_file(fingerprint: str) -> dict:
    """删除文件索引"""
    from src.tools.kb_vector import VectorIndexer

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM files WHERE fingerprint = ?", (fingerprint,))
    conn.execute(
        "DELETE FROM keyword_index WHERE chunk_id LIKE ?", (f"{fingerprint}-%",)
    )
    conn.commit()
    conn.close()

    vector_indexer = VectorIndexer()
    vector_indexer.remove(fingerprint)

    chunk_file = os.path.join(CHUNKS_DIR, fingerprint[:2], f"{fingerprint}.json")
    if os.path.exists(chunk_file):
        os.remove(chunk_file)

    if os.path.exists(INDEX_JSON):
        with open(INDEX_JSON, "r", encoding="utf-8") as f:
            index_data = json.load(f)
        if fingerprint in index_data:
            del index_data[fingerprint]
            with open(INDEX_JSON, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

    return {"success": True, "message": f"已删除指纹 {fingerprint} 的索引"}


def get_kb_context_block() -> str:
    """获取知识库上下文文本（注入到对话上下文）"""
    result = _kb_list_indexed()
    if not result.get("success") or not result.get("files"):
        return ""

    files = result["files"]
    if not files:
        return ""

    lines = ["## 已索引文件列表"]
    for f in files:
        lines.append(
            f"- {f['name']} (指纹: {f['fingerprint']}, 块数: {f.get('chunks_count', 0)})"
        )

    return "\n".join(lines)
