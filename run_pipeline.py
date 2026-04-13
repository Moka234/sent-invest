"""
run_pipeline.py
===============
SentInvest 工业级自动化调度引擎
流批一体化 Pipeline：Spark清洗 -> FinBERT情感分析 -> 用户风控画像

运行方式：
  pip install schedule
  python run_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime

import schedule

# ─────────────────────────────────────────────
# ANSI 颜色常量（终端彩色输出）
# ─────────────────────────────────────────────
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ─────────────────────────────────────────────
# Pipeline 步骤定义（DAG）
# ─────────────────────────────────────────────
STEPS = [
    ("Step 1 · Spark 文本清洗",       "python pipeline/cleaner.py"),
    ("Step 2 · FinBERT 情感分析",     "python pipeline/analyzer.py"),
    ("Step 3 · 用户风控画像聚合",     "python pipeline/profiler.py"),
]


def log(msg: str) -> None:
    """带时间戳的统一日志输出。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{CYAN}[{ts}]{RESET} {msg}")


def run_step(step_name: str, command: str) -> bool:
    """
    执行单步 Pipeline 命令。

    Args:
        step_name: 步骤名称（用于日志展示）
        command:   Shell 命令字符串

    Returns:
        True  - 执行成功
        False - 执行失败（不退出主进程，等待下次调度）
    """
    log(f"{BOLD}{YELLOW}▶ 开始：{step_name}{RESET}")
    start = time.perf_counter()

    try:
        subprocess.run(
            command,
            shell=True,
            check=True,          # 非零退出码抛出 CalledProcessError
            cwd=".",             # 工作目录：项目根目录
        )
        elapsed = time.perf_counter() - start
        log(f"{GREEN}✓ {step_name} 执行成功，耗时: {elapsed:.1f}s{RESET}")
        return True

    except subprocess.CalledProcessError as e:
        elapsed = time.perf_counter() - start
        log(
            f"{RED}{BOLD}✗ [ERROR] {step_name} 执行失败！"
            f"\n  命令   : {command}"
            f"\n  退出码 : {e.returncode}"
            f"\n  耗时   : {elapsed:.1f}s"
            f"\n  主进程不退出，等待下一次调度...{RESET}"
        )
        return False  # ← 阻断本轮次后续步骤，但守护进程继续运行


def job() -> None:
    """
    完整 Pipeline 编排函数（The DAG）。
    严格按顺序执行各步骤；任一步骤失败则中止本轮次。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print()
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  🚀 SentInvest Pipeline 调度引擎 · {now}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    job_start = time.perf_counter()

    for step_name, command in STEPS:
        success = run_step(step_name, command)
        if not success:
            log(
                f"{RED}{BOLD}⚠ 当前轮次因 [{step_name}] 失败而提前中止。"
                f"等待下一次定时调度...{RESET}"
            )
            print(f"{CYAN}{'─' * 60}{RESET}\n")
            return

    total = time.perf_counter() - job_start
    print()
    print(f"{BOLD}{GREEN}{'═' * 60}{RESET}")
    print(
        f"{BOLD}{GREEN}  🎉 完整 Pipeline 执行成功！"
        f"总耗时: {total:.1f}s   等待下一次调度...{RESET}"
    )
    print(f"{BOLD}{GREEN}{'═' * 60}{RESET}\n")


if __name__ == "__main__":
    print()
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  SentInvest 自动化调度引擎 启动{RESET}")
    print(f"{BOLD}{CYAN}  调度策略：启动时立即执行 + 每 1 小时触发一次{RESET}")
    print(f"{BOLD}{CYAN}  按 Ctrl+C 可安全退出守护进程{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}\n")

    # ── 1. 启动时立刻执行一次全量跑批 ──
    job()

    # ── 2. 注册定时策略：每 1 小时触发一次 ──
    schedule.every(1).hours.do(job)
    log(f"{YELLOW}定时任务已注册：每 1 小时触发一次 Pipeline{RESET}")

    # ── 3. 守护进程主循环 ──
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        log(f"{YELLOW}收到 Ctrl+C，调度引擎安全退出。{RESET}")
        sys.exit(0)
