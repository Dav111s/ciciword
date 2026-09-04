# ai/memory_model.py
"""
遗忘预测神经网络：PyTorch 训练 + ONNX Runtime 推理。

模型结构：
    输入层  8 个特征
    隐藏层1 32 神经元, ReLU
    隐藏层2 16 神经元, ReLU
    输出层  1 神经元, Sigmoid -> 遗忘概率 (0~1)

特征（8 维，见 FEATURE_NAMES）：
    1. 历史复习总次数
    2. 历史平均正确率
    3. 最近一次复习间隔天数 gap_days
    4. 距离上次复习过去的天数
    5. 连续答对次数
    6. 连续答错次数
    7. 单词难度（初始 0.5，由历史错误率更新）
    8. 用户全局平均正确率

训练数据说明（重要简化）：
    records 表未保存每条记录“当时”的完整特征快照，因此训练样本的特征使用
    该单词“当前”状态近似当时状态（有偏但可接受的简化），见 build_training_data()。

推理：优先使用 ONNX Runtime（CPU，移动端友好）；模型不存在或记录数不足时
    回退到简化 SM-2 规则。torch 仅训练时按需导入，移动端可只装 onnxruntime。
"""
import json
import math
import os
import threading
import time
from datetime import datetime

import numpy as np

from config import MIN_TRAIN_SAMPLES, RETRAIN_INTERVAL_SECONDS
from data import db
from paths import model_pth_path, model_onnx_path, train_meta_path

FEATURE_NAMES = [
    'history_count', 'avg_correct', 'last_gap_days',
    'days_since_last_review', 'streak_correct', 'streak_wrong',
    'difficulty', 'global_avg_correct',
]

INPUT_DIM = 8


# ------------------------- 特征工程 -------------------------

def _log1p(x) -> float:
    return math.log1p(max(0.0, float(x)))


def extract_features(word_id):
    """
    提取单词当前状态的特征向量（8 维，已归一化）。
    计数类特征取 log1p 压缩，比率类特征保持 [0,1]。
    无单词或无法计算时返回 None。
    """
    word = db.get_word_by_id(word_id)
    if word is None:
        return None

    recs = db.get_review_records_for_word(word_id, include_learn=True)
    n = len(recs)
    avg_correct = (sum(1 for r in recs if r['is_right']) / n) if n else 0.5

    last_gap = 0
    if recs:
        last_gap = recs[-1]['gap_days'] if recs[-1]['gap_days'] is not None else 0

    days_since = 0
    if word.get('last_review_day'):
        try:
            last = datetime.strptime(word['last_review_day'], '%Y-%m-%d').date()
            days_since = max(0, (datetime.now().date() - last).days)
        except (ValueError, TypeError):
            days_since = 0

    # 末尾连续答对 / 连续答错次数
    streak_correct = 0
    for r in reversed(recs):
        if r['is_right']:
            streak_correct += 1
        else:
            break
    streak_wrong = 0
    for r in reversed(recs):
        if not r['is_right']:
            streak_wrong += 1
        else:
            break

    difficulty = float(word.get('difficulty') or 0.5)
    global_acc = db.get_global_avg_correct()

    features = np.array([
        _log1p(n),               # 1. 历史复习总次数
        float(avg_correct),      # 2. 平均正确率
        _log1p(last_gap),        # 3. 最近间隔天数
        _log1p(days_since),      # 4. 距上次复习天数
        _log1p(streak_correct),  # 5. 连续答对
        _log1p(streak_wrong),    # 6. 连续答错
        max(0.0, min(1.0, difficulty)),  # 7. 难度
        float(global_acc),       # 8. 全局正确率
    ], dtype=np.float32)
    return features


# ------------------------- 神经网络（PyTorch） -------------------------

def build_model():
    import torch
    import torch.nn as nn

    class ForgettingNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(INPUT_DIM, 32),
                nn.ReLU(),
                nn.Linear(32, 16),
                nn.ReLU(),
                nn.Linear(16, 1),
                nn.Sigmoid(),
            )

        def forward(self, x):
            return self.net(x)

    return ForgettingNet()


def build_training_data():
    """
    从 records 构造训练样本 (X, y)。

    简化说明：records 未保存每条记录当时的特征快照，此处用“当前特征”近似
    当时状态（有偏但可接受）。样本标签 = 是否遗忘（is_right=0 -> 遗忘概率 1）。
    记录数 < MIN_TRAIN_SAMPLES 时返回 (None, None)。
    """
    recs = db.get_all_review_records()
    feat_cache = {}
    X, y = [], []
    for r in recs:
        wid = r['word_id']
        if wid not in feat_cache:
            feat_cache[wid] = extract_features(wid)
        f = feat_cache[wid]
        if f is None:
            continue
        X.append(f)
        y.append(0.0 if r['is_right'] else 1.0)
    if len(X) < MIN_TRAIN_SAMPLES:
        return None, None
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.float32).reshape(-1, 1)
    return X, y


def _save_train_meta(num_samples):
    meta = {'last_train_ts': time.time(), 'num_samples': num_samples}
    try:
        with open(train_meta_path(), 'w', encoding='utf-8') as f:
            json.dump(meta, f)
    except OSError:
        pass


def train_model(force=False) -> bool:
    """
    训练模型并保存 .pth，同时导出 .onnx 供 ONNX Runtime 推理。
    训练成功后返回 True。
    """
    if not force and not should_train():
        return False

    X, y = build_training_data()
    if X is None or len(X) < MIN_TRAIN_SAMPLES:
        return False

    import torch
    import torch.nn as nn

    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()
    Xt = torch.from_numpy(X)
    yt = torch.from_numpy(y)

    model.train()
    for _ in range(80):
        opt.zero_grad()
        pred = model(Xt)
        loss = loss_fn(pred, yt)
        loss.backward()
        opt.step()
    model.eval()

    try:
        torch.save(model.state_dict(), str(model_pth_path()))
    except OSError:
        return False

    # 导出 ONNX（CPU 推理用）
    # 注意：torch.onnx.export 会向 stdout 打印含 emoji 的日志，
    # Windows GBK 控制台无法编码会抛 UnicodeEncodeError，故重定向 stdout。
    import contextlib
    import io
    try:
        dummy = torch.zeros(1, INPUT_DIM, dtype=torch.float32)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            torch.onnx.export(
                model, dummy, str(model_onnx_path()),
                input_names=['features'], output_names=['prob'],
                opset_version=13,
            )
    except Exception:
        pass

    _save_train_meta(len(X))
    reset_session()
    return True


def train_async(force=False):
    """后台线程增量训练，避免阻塞界面。"""
    def _run():
        try:
            train_model(force=force)
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ------------------------- ONNX Runtime 推理 -------------------------

_session = None
_session_path = None


def _get_session():
    global _session, _session_path
    onnx_path = str(model_onnx_path())
    if _session is not None and _session_path == onnx_path:
        return _session
    if not os.path.exists(onnx_path):
        return None
    try:
        import onnxruntime as ort
        _session = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
        _session_path = onnx_path
        return _session
    except Exception:
        return None


def reset_session():
    global _session, _session_path
    _session = None
    _session_path = None


def has_model() -> bool:
    return os.path.exists(model_onnx_path())


def predict_forget_probability(features):
    """
    给定 8 维特征，输出遗忘概率 0~1。
    无可用模型时返回 None（调用方应回退到规则）。
    """
    sess = _get_session()
    if sess is None:
        return None
    x = np.asarray(features, dtype=np.float32).reshape(1, -1)
    try:
        out = sess.run(['prob'], {'features': x})[0]
    except Exception:
        return None
    p = float(np.asarray(out).reshape(-1)[0])
    return max(0.0, min(1.0, p))


# ------------------------- 间隔换算 -------------------------

def calc_next_interval(forget_prob, stability=1.0) -> int:
    """平滑间隔公式：interval = stability * (1 - forget_prob)^1.5。"""
    p = max(0.0, min(1.0, float(forget_prob)))
    s = max(0.3, float(stability or 1.0))
    interval = s * (1.0 - p) ** 1.5
    return int(max(1, min(365, round(interval))))


def calc_next_interval_sm2(is_right, gap_days, stability=1.0) -> int:
    """简化 SM-2（回退规则）：答对间隔翻倍，答错回到 1 天。"""
    if is_right:
        return int(max(1, min(365, max(1, int(gap_days or 1)) * 2)))
    return 1


def recommend_interval(word_id, is_right, gap_days) -> dict:
    """
    综合给出复习建议。返回 dict：
      interval      下次间隔（天）
      forget_prob   预测遗忘概率（None 表示未用模型）
      new_stability / new_difficulty / new_lapses  更新后的记忆状态
      used_model    是否使用了神经网络
    """
    word = db.get_word_by_id(word_id)
    stability = float(word['stability']) if word and word.get('stability') else 1.0
    difficulty = float(word['difficulty']) if word and word.get('difficulty') else 0.5
    lapses = int(word['lapses']) if word and word.get('lapses') else 0

    forget_prob = None
    used_model = False
    if has_model() and db.get_record_count('review') >= MIN_TRAIN_SAMPLES:
        feats = extract_features(word_id)
        if feats is not None:
            forget_prob = predict_forget_probability(feats)
    if forget_prob is not None:
        used_model = True
        interval = calc_next_interval(forget_prob, stability)
    else:
        interval = calc_next_interval_sm2(is_right, gap_days, stability)

    # 更新记忆状态
    if is_right:
        new_stability = min(30.0, stability * 1.4)
        new_lapses = lapses
    else:
        new_stability = max(0.5, stability * 0.6)
        new_lapses = lapses + 1
    new_difficulty = max(0.0, min(1.0, 0.9 * difficulty + (0.0 if is_right else 0.1)))

    return {
        'interval': interval,
        'forget_prob': forget_prob,
        'new_stability': round(new_stability, 4),
        'new_difficulty': round(new_difficulty, 4),
        'new_lapses': new_lapses,
        'used_model': used_model,
    }


# ------------------------- 训练时机 -------------------------

def should_train() -> bool:
    """记录数足够且（无模型或距上次训练超过阈值）则允许训练。"""
    if db.get_record_count('review') < MIN_TRAIN_SAMPLES:
        return False
    if not has_model():
        return True
    try:
        with open(train_meta_path(), 'r', encoding='utf-8') as f:
            meta = json.load(f)
        last = meta.get('last_train_ts', 0)
    except (OSError, json.JSONDecodeError):
        last = 0
    return (time.time() - last) >= RETRAIN_INTERVAL_SECONDS
