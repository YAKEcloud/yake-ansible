def test_kind_install_script(host):
    f = host.file("/usr/local/bin/kind")
    assert f.exists
    assert not f.is_directory
    assert f.mode == 0o755
    assert "#!/usr/bin/env bash" in f.content_string
