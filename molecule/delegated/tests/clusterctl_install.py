def test_clusterctl_install_script(host):
    f = host.file("/usr/local/bin/yake-clusterctl")
    assert f.exists
    assert not f.is_directory
    assert f.mode == 0o755
    assert "#!/usr/bin/env bash" in f.content_string


def test_clusterctl_install_container(host):
    container_name = "clusterctl"
    container = host.docker(container_name)
    assert container.is_running
