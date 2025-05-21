def test_kubectl_install_script(host):
    f = host.file("/usr/local/bin/yake-kubectl")
    assert f.exists
    assert not f.is_directory
    assert f.mode == 0o755
    assert "#!/usr/bin/env bash" in f.content_string


def test_kubectl_install_container(host):
    container_name = "kubectl"
    container = host.docker(container_name)
    assert container.is_running
