# -*- coding: utf-8 -*-
"""Compatibility entrypoint for Pinduoduo Android order screenshots."""

from __future__ import annotations

from android_order_bot import main


if __name__ == "__main__":
    raise SystemExit(main(default_platform="pdd"))
