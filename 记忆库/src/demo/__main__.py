"""
演示入口脚本
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.demo.orchestrator import DemoOrchestrator


def main():
    orchestrator = DemoOrchestrator(log_dir="demo_logs")
    orchestrator.run()


if __name__ == "__main__":
    main()
