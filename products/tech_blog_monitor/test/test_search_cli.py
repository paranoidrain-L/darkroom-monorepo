# -*- coding: utf-8 -*-
"""Tech Blog Monitor search_cli 单元测试。"""

import pytest

from products.tech_blog_monitor.search_cli import main


def test_search_cli_missing_db_exits_nonzero(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing.db"
    monkeypatch.setattr(
        "sys.argv",
        ["search_cli.py", "--db", str(missing), "--query", "agent"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "资产库不存在" in captured.err
    assert not missing.exists()
