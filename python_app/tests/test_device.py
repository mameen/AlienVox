"""Tests for src/device.py's CUDA detection.

Split into two groups:
  - Mocked tests (always run): verify select_device()/cuda_available() react
    correctly to torch.cuda.is_available()/device_count() including the
    is_available()==True-but-device_count()==0 edge case that caused a real
    bug in health.py and run.py's --gpu fail-fast check.
  - Hardware tests (requires_gpu, skipped on CPU-only machines/CI): verify
    against whatever GPU is actually attached, so this suite proves real
    devices are picked up correctly on machines that have them.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.device import cuda_available, select_device

from .conftest import requires_gpu


# ── Mocked: is_available() + device_count() combinations ────────────────────

def test_cuda_unavailable_when_is_available_false():
    with patch("torch.cuda.is_available", return_value=False):
        assert cuda_available() is False


def test_cuda_unavailable_when_device_count_zero():
    """The bug this module exists to fix: is_available()=True doesn't
    guarantee a usable device (e.g. under CUDA_VISIBLE_DEVICES="")."""
    with patch("torch.cuda.is_available", return_value=True), \
         patch("torch.cuda.device_count", return_value=0):
        assert cuda_available() is False


def test_cuda_available_when_device_count_positive():
    with patch("torch.cuda.is_available", return_value=True), \
         patch("torch.cuda.device_count", return_value=1):
        assert cuda_available() is True


def test_cuda_unavailable_on_import_error():
    with patch.dict("sys.modules", {"torch": None}):
        assert cuda_available() is False


def test_select_device_returns_cpu_when_unavailable():
    with patch("src.device.cuda_available", return_value=False):
        assert select_device() == "cpu"


def test_select_device_returns_cuda_when_available():
    with patch("src.device.cuda_available", return_value=True):
        assert select_device() == "cuda"


# ── Hardware: only run on a machine with a real CUDA GPU ─────────────────────

@requires_gpu
def test_real_hardware_cuda_available():
    assert cuda_available() is True


@requires_gpu
def test_real_hardware_select_device_is_cuda():
    assert select_device() == "cuda"


@requires_gpu
def test_real_hardware_device_count_positive():
    import torch
    assert torch.cuda.device_count() > 0


@requires_gpu
def test_real_hardware_device_name_is_nonempty():
    import torch
    name = torch.cuda.get_device_properties(0).name
    assert isinstance(name, str) and len(name) > 0
