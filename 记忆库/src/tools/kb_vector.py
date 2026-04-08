"""知识库向量索引模块

使用 BGE 模型（ONNX Runtime）+ FAISS 向量搜索
- BGE 模型复用 association_scorer.py 的路径
- FAISS 做相似度搜索（CPU 版本，Windows 无官方 GPU 包）
- 向量按 fingerprint 分片持久化为 JSON
"""

import os
import json
import logging
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

KB_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "知识库")
MODEL_DIR = os.path.join(KB_DIR, ".models", "bge-small-zh-v1.5")
ONNX_PATH = os.path.join(MODEL_DIR, "onnx", "model.onnx")
TOKENIZER_PATH = MODEL_DIR
INDEX_DIR = os.path.join(KB_DIR, ".index", "vector")
DIMENSION = 512
INSTRUCT = "为这个句子生成表示以用于检索相关文章："

_faiss_index = None
_embedding_session = None
_tokenizer = None


def _get_embedding_model():
    """懒加载 BGE ONNX 模型"""
    global _embedding_session, _tokenizer
    if _embedding_session is not None:
        return _embedding_session, _tokenizer

    try:
        import onnxruntime as ort
        from transformers import BertTokenizer

        _tokenizer = BertTokenizer.from_pretrained(
            TOKENIZER_PATH, local_files_only=True
        )
        _embedding_session = ort.InferenceSession(
            ONNX_PATH, providers=["CPUExecutionProvider"]
        )
        logger.info("BGE 向量模型加载成功")
    except Exception as e:
        logger.error(f"BGE 向量模型加载失败: {e}")
        return None, None

    return _embedding_session, _tokenizer


def _get_faiss_index():
    """懒加载/创建 FAISS 索引"""
    global _faiss_index
    if _faiss_index is not None:
        return _faiss_index

    try:
        import faiss

        _faiss_index = faiss.IndexFlatIP(DIMENSION)  # 内积（已归一化向量 = 余弦相似度）
        logger.info("FAISS 索引创建成功")
    except Exception as e:
        logger.error(f"FAISS 初始化失败: {e}")
        return None

    return _faiss_index


def _encode_batch(texts: list[str]) -> np.ndarray:
    """批量编码文本为归一化向量"""
    session, tokenizer = _get_embedding_model()
    if session is None or tokenizer is None:
        return np.array([])

    texts = [INSTRUCT + t for t in texts]
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="np",
    )

    input_names = [i.name for i in session.get_inputs()]
    feed = {
        "input_ids": encoded["input_ids"].astype(np.int64),
        "attention_mask": encoded["attention_mask"].astype(np.int64),
    }
    if "token_type_ids" in input_names:
        feed["token_type_ids"] = encoded["token_type_ids"].astype(np.int64)

    outputs = session.run(None, feed)[0]
    embeddings = outputs[:, 0]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms
    return embeddings


class VectorIndexer:
    """向量索引器（FAISS 存储 + JSON 备份）"""

    def __init__(self):
        self.id_to_idx = {}
        self.idx_to_id = {}
        self.vector_cache = {}

    def _load_fingerprint(self, fingerprint: str):
        """从 JSON 备份加载某个 fingerprint 的向量"""
        shard = fingerprint[:2]
        vec_file = os.path.join(INDEX_DIR, shard, f"{fingerprint}.vectors.json")
        if not os.path.exists(vec_file):
            return

        try:
            vecs = json.loads(open(vec_file, "r", encoding="utf-8").read())
            for chunk_id, vec in vecs.items():
                self.vector_cache[chunk_id] = vec
        except Exception as e:
            logger.warning(f"加载向量备份失败 {fingerprint}: {e}")

    def restore_from_backup(self):
        """从所有 JSON 备份恢复索引"""
        if not os.path.exists(INDEX_DIR):
            return

        faiss = _get_faiss_index()
        if faiss is None:
            return

        total = 0
        for shard_dir in os.listdir(INDEX_DIR):
            shard_path = os.path.join(INDEX_DIR, shard_dir)
            if not os.path.isdir(shard_path):
                continue
            for fname in os.listdir(shard_path):
                if fname.endswith(".vectors.json"):
                    fingerprint = fname.replace(".vectors.json", "")
                    self._load_fingerprint(fingerprint)
                    total += 1

        if self.vector_cache:
            vectors = []
            ids = []
            for chunk_id, vec in self.vector_cache.items():
                vectors.append(vec)
                ids.append(chunk_id)

            if vectors:
                vec_array = np.array(vectors, dtype=np.float32)
                faiss.add(vec_array)
                for i, cid in enumerate(ids):
                    self.id_to_idx[cid] = i
                    self.idx_to_id[i] = cid

            logger.info(
                f"从备份恢复 {total} 个文件，共 {len(self.vector_cache)} 个向量"
            )

    def is_ready(self) -> bool:
        return _get_embedding_model()[0] is not None and _get_faiss_index() is not None

    def add(self, chunk_id: str, text: str):
        """为单个 chunk 生成向量并加入索引"""
        vec = _encode_batch([text])
        if vec.size == 0:
            return
        vector = vec[0].tolist()

        faiss = _get_faiss_index()
        if faiss is None:
            return

        vec_array = np.array([vector], dtype=np.float32)

        if chunk_id in self.id_to_idx:
            old_idx = self.id_to_idx[chunk_id]
            faiss.remove_ids(np.array([old_idx], dtype=np.int64))
            del self.idx_to_id[old_idx]

        new_idx = faiss.ntotal
        faiss.add(vec_array)
        self.id_to_idx[chunk_id] = new_idx
        self.idx_to_id[new_idx] = chunk_id
        self.vector_cache[chunk_id] = vector

    def add_batch(self, chunks: list):
        """批量添加向量索引

        Args:
            chunks: [{id, text}, ...]
        """
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        vecs = _encode_batch(texts)
        if vecs.size == 0:
            return

        faiss = _get_faiss_index()
        if faiss is None:
            return

        vec_array = vecs.astype(np.float32)

        for chunk in chunks:
            if chunk["id"] in self.id_to_idx:
                old_idx = self.id_to_idx[chunk["id"]]
                if old_idx in self.idx_to_id:
                    del self.idx_to_id[old_idx]
                del self.id_to_idx[chunk["id"]]

        start_idx = faiss.ntotal
        faiss.add(vec_array)

        for i, chunk in enumerate(chunks):
            idx = start_idx + i
            self.id_to_idx[chunk["id"]] = idx
            self.idx_to_id[idx] = chunk["id"]
            self.vector_cache[chunk["id"]] = vecs[i].tolist()

    def search(self, query: str, top_k: int = 5) -> list:
        """语义搜索

        Returns:
            [{chunkId, score}, ...]
        """
        faiss = _get_faiss_index()
        if faiss is None or faiss.ntotal == 0:
            return []

        qv = _encode_batch([query])
        if qv.size == 0:
            return []

        qv_array = qv.astype(np.float32)
        k = min(top_k * 2, faiss.ntotal)
        scores, indices = faiss.search(qv_array, k)

        results = []
        for i in range(len(indices[0])):
            idx = int(indices[0][i])
            if idx in self.idx_to_id:
                results.append(
                    {
                        "chunkId": self.idx_to_id[idx],
                        "score": float(scores[0][i]),
                    }
                )
        return results

    def save(self, fingerprint: str):
        """保存某个 fingerprint 的向量为 JSON 备份"""
        shard = fingerprint[:2]
        dir_path = os.path.join(INDEX_DIR, shard)
        os.makedirs(dir_path, exist_ok=True)

        ids = [cid for cid in self.vector_cache if cid.startswith(fingerprint)]
        vecs = {cid: self.vector_cache[cid] for cid in ids}

        vec_file = os.path.join(dir_path, f"{fingerprint}.vectors.json")
        with open(vec_file, "w", encoding="utf-8") as f:
            json.dump(vecs, f, ensure_ascii=False)

        meta = {
            "fingerprint": fingerprint,
            "chunkCount": len(ids),
            "dimension": DIMENSION,
            "ids": ids,
            "createdAt": str(__import__("datetime").datetime.now().isoformat()),
        }
        meta_file = os.path.join(dir_path, f"{fingerprint}.meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def remove(self, fingerprint: str):
        """删除某个 fingerprint 的所有向量"""
        shard = fingerprint[:2]
        dir_path = os.path.join(INDEX_DIR, shard)

        ids_to_remove = [
            cid for cid in self.vector_cache if cid.startswith(fingerprint)
        ]
        for cid in ids_to_remove:
            if cid in self.id_to_idx:
                idx = self.id_to_idx[cid]
                faiss = _get_faiss_index()
                if faiss:
                    try:
                        faiss.remove_ids(np.array([idx], dtype=np.int64))
                    except Exception:
                        pass
                if idx in self.idx_to_id:
                    del self.idx_to_id[idx]
                del self.id_to_idx[cid]
                del self.vector_cache[cid]

        for ext in ("vectors.json", "meta.json"):
            f = os.path.join(dir_path, f"{fingerprint}.{ext}")
            if os.path.exists(f):
                os.remove(f)
