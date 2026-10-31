"""Điểm vào của TodoLite. Nhấp đúp để mở; đuôi .pyw giúp chạy không hiện cửa sổ console."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from todolite.cli import main  # noqa: E402

main(sys.argv[1:])
