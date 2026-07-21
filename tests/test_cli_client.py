"""Tests for cli_client 模块。

覆盖：
- ``get_api_base``：从 ``user_config.json`` 读取 API 地址（含 0.0.0.0 转换、回退默认）
- ``check_main_process``：探活成功与失败路径
- ``add_instance``：请求体构造、position 省略、HTTP 错误处理
- ``list_instances``：返回列表解析

所有 HTTP 调用均用 ``unittest.mock.patch`` 替换 ``httpx.Client``，不发起真实请求。
"""
import json
from unittest.mock import patch, MagicMock

import httpx
import pytest

from desktop_pet import cli_client
from desktop_pet.cli_client import CliError


# ---------------------------------------------------------------------------
# get_api_base
# ---------------------------------------------------------------------------
def test_get_api_base_reads_user_config(tmp_path):
    """写入 user_config.json 含 api.port=9090，断言返回 http://127.0.0.1:9090"""
    cfg = tmp_path / "user_config.json"
    cfg.write_text(
        json.dumps({"api": {"host": "127.0.0.1", "port": 9090}}), encoding="utf-8"
    )
    assert cli_client.get_api_base(tmp_path) == "http://127.0.0.1:9090"


def test_get_api_base_converts_wildcard_host(tmp_path):
    """host=0.0.0.0 时转为 127.0.0.1（CLI 总是连本机）"""
    cfg = tmp_path / "user_config.json"
    cfg.write_text(
        json.dumps({"api": {"host": "0.0.0.0", "port": 8080}}), encoding="utf-8"
    )
    assert cli_client.get_api_base(tmp_path) == "http://127.0.0.1:8080"


def test_get_api_base_fallback_default(tmp_path):
    """无配置文件时回退默认 http://127.0.0.1:8080"""
    # tmp_path 内无 user_config.json
    assert cli_client.get_api_base(tmp_path) == "http://127.0.0.1:8080"


# ---------------------------------------------------------------------------
# check_main_process
# ---------------------------------------------------------------------------
def test_check_main_process_success():
    """mock httpx.Client.get 返回 200，断言返回 True"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.get.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        assert cli_client.check_main_process("http://127.0.0.1:8080") is True


def test_check_main_process_failure():
    """mock httpx.Client.get 抛 ConnectError，断言返回 False"""
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.get.side_effect = httpx.ConnectError("connection refused")
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        assert cli_client.check_main_process("http://127.0.0.1:8080") is False


# ---------------------------------------------------------------------------
# add_instance
# ---------------------------------------------------------------------------
def test_add_instance_sends_correct_payload():
    """mock httpx.Client.post，断言请求体与 URL 正确"""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "pet_id": "abc123",
        "package": "default",
        "position": {"x": 500, "y": 300},
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.add_instance(
            "http://127.0.0.1:8080", "default", 500, 300
        )
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/instances",
        json={"package": "default", "position": {"x": 500, "y": 300}},
    )
    assert result["pet_id"] == "abc123"


def test_add_instance_omits_position_when_both_none():
    """x/y 均为 None 时，payload 不含 position（由主进程使用包默认值）"""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"pet_id": "abc", "package": "default"}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.add_instance("http://127.0.0.1:8080", "default", None, None)
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/instances",
        json={"package": "default"},
    )


def test_add_instance_raises_on_http_error():
    """mock 返回 400，断言抛 CliError"""
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "bad request"
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        with pytest.raises(CliError, match="创建实例失败"):
            cli_client.add_instance("http://127.0.0.1:8080", "default", 0, 0)


# ---------------------------------------------------------------------------
# list_instances
# ---------------------------------------------------------------------------
def test_list_instances_returns_list():
    """mock 返回 {"instances": [...]}，断言返回列表"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "instances": [{"pet_id": "a", "package": "default"}]
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.get.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.list_instances("http://127.0.0.1:8080")
    assert isinstance(result, list)
    assert result[0]["pet_id"] == "a"


# ---------------------------------------------------------------------------
# remove_instance
# ---------------------------------------------------------------------------
def test_remove_instance_sends_delete():
    """mock httpx.Client.delete 返回 200，断言调用 URL 正确且无返回值"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.delete.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.remove_instance("http://127.0.0.1:8080", "abc123")
    mock_client.delete.assert_called_once_with(
        "http://127.0.0.1:8080/api/instances/abc123"
    )
    assert result is None


def test_remove_instance_raises_on_404():
    """mock 返回 404，断言抛 CliError 提示实例不存在"""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = '{"error": "pet not found"}'
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.delete.return_value = mock_resp
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        with pytest.raises(CliError, match="实例不存在：pet_id=abc123"):
            cli_client.remove_instance("http://127.0.0.1:8080", "abc123")


def test_remove_instance_raises_on_http_error():
    """mock 抛 ConnectError，断言抛 CliError"""
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.delete.side_effect = httpx.ConnectError("refused")
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        with pytest.raises(CliError, match="连接主进程失败"):
            cli_client.remove_instance("http://127.0.0.1:8080", "abc123")


def test_remove_instance_rejects_empty_pet_id():
    """空字符串 pet_id 抛 CliError（防御性）"""
    with pytest.raises(CliError, match="pet_id 不能为空"):
        cli_client.remove_instance("http://127.0.0.1:8080", "")


# ---------------------------------------------------------------------------
# 控制类指令：play_animation / walk_pet / move_to / move_by / move_edge / list_animations
# ---------------------------------------------------------------------------
def _make_mock_client(method: str, resp: MagicMock) -> MagicMock:
    """构造 mock httpx.Client，指定方法（get/post）返回 resp。"""
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    setattr(mock_client, method, MagicMock(return_value=resp))
    return mock_client


def test_play_animation_sends_correct_payload():
    """POST /api/pets/<pet_id>/animation 请求体 {"name": "sit"}"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "animation": "sit"}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.play_animation("http://127.0.0.1:8080", "abc", "sit")
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/animation",
        json={"name": "sit"},
    )
    assert result["success"] is True


def test_play_animation_raises_on_http_error():
    """HTTP 400 抛 CliError"""
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "unknown animation"
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        with pytest.raises(CliError, match="指令失败"):
            cli_client.play_animation("http://127.0.0.1:8080", "abc", "unknown")


def test_walk_pet_sends_correct_payload():
    """POST /api/pets/<pet_id>/walk 请求体 {"direction": "left"}"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.walk_pet("http://127.0.0.1:8080", "abc", "left")
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/walk",
        json={"direction": "left"},
    )


def test_move_to_sends_correct_payload():
    """POST /api/pets/<pet_id>/move 请求体 {"x": 100, "y": 200}（无 screen）"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.move_to("http://127.0.0.1:8080", "abc", 100, 200)
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/move",
        json={"x": 100, "y": 200},
    )


def test_move_to_with_screen():
    """screen 非 None 时请求体含 "screen": 1"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.move_to("http://127.0.0.1:8080", "abc", 100, 200, screen=1)
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/move",
        json={"x": 100, "y": 200, "screen": 1},
    )


def test_move_by_sends_correct_payload():
    """POST /api/pets/<pet_id>/move_by 请求体 {"dx": 50, "dy": 0}"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.move_by("http://127.0.0.1:8080", "abc", 50, 0)
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/move_by",
        json={"dx": 50, "dy": 0},
    )


def test_move_edge_sends_correct_payload():
    """POST /api/pets/<pet_id>/move_edge 请求体 {"edge": "left"}"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.move_edge("http://127.0.0.1:8080", "abc", "left")
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/move_edge",
        json={"edge": "left"},
    )


def test_list_animations_returns_list():
    """GET /api/pets/<pet_id>/animations 返回动画名列表"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"animations": ["sit", "walk", "sleep"]}
    mock_client = _make_mock_client("get", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.list_animations("http://127.0.0.1:8080", "abc")
    mock_client.get.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/animations"
    )
    assert result == ["sit", "walk", "sleep"]


def test_post_pet_command_rejects_empty_pet_id():
    """空字符串 pet_id 抛 CliError（防御性）"""
    with pytest.raises(CliError, match="pet_id 不能为空"):
        cli_client.play_animation("http://127.0.0.1:8080", "", "sit")
    with pytest.raises(CliError, match="pet_id 不能为空"):
        cli_client.list_animations("http://127.0.0.1:8080", "")


# ---------------------------------------------------------------------------
# show_bubble / hide_bubble
# ---------------------------------------------------------------------------
def test_show_bubble_sends_correct_payload():
    """POST /api/pets/<pet_id>/message 请求体 {"text": "...", "duration": 0}"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.show_bubble("http://127.0.0.1:8080", "abc", "你好")
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/message",
        json={"text": "你好", "duration": 0},
    )
    assert result == {"success": True}


def test_show_bubble_with_duration():
    """duration > 0 时正确传入"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        cli_client.show_bubble("http://127.0.0.1:8080", "abc", "提示", duration=3000)
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/message",
        json={"text": "提示", "duration": 3000},
    )


def test_hide_bubble_sends_correct_request():
    """POST /api/pets/<pet_id>/message/hide 请求体 {}"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_client = _make_mock_client("post", mock_resp)
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        result = cli_client.hide_bubble("http://127.0.0.1:8080", "abc")
    mock_client.post.assert_called_once_with(
        "http://127.0.0.1:8080/api/pets/abc/message/hide",
        json={},
    )
    assert result == {"success": True}


def test_show_bubble_raises_on_http_error():
    """mock 抛 ConnectError，断言抛 CliError"""
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = httpx.ConnectError("refused")
    with patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client):
        with pytest.raises(CliError, match="连接主进程失败"):
            cli_client.show_bubble("http://127.0.0.1:8080", "abc", "你好")
