def test_kind_cluster_container(host):
    container_name = "clusterapi-control-plane"
    container = host.docker(container_name)
    assert container.is_running


def test_kind_cluster_kubeconfig(host):
    """Test if the kubeconfig file exists and has correct permissions."""
    kubeconfig = host.file("/var/lib/yake/kubeconfig.clusterapi")
    assert kubeconfig.exists
    assert kubeconfig.mode == 0o640
    assert not kubeconfig.is_directory


def test_kind_cluster_running(host):
    """Test if the KIND cluster is up and running with yake-kubectl."""
    # Check if yake-kubectl can connect to the cluster using the kubeconfig
    cmd = host.run(
        "KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi yake-kubectl get nodes"
    )
    assert cmd.rc == 0
    assert "clusterapi-control-plane" in cmd.stdout

    # Check if nodes are in Ready status
    cmd = host.run(
        "KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi yake-kubectl get nodes -o jsonpath='{.items[*].status.conditions[?(@.type==\"Ready\")].status}'"  # noqa E501
    )
    assert cmd.rc == 0
    assert "True" in cmd.stdout
