def test_kind_cluster_container(host):
    container_name = "clusterapi-control-plane"
    container = host.docker(container_name)
    assert container.is_running
