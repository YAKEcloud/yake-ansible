def test_kind_cluster_container(host):
    container_name = "yake-control-plane"
    container = host.docker(container_name)
    assert container.is_running
