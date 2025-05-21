def test_clusterapi_install_crds(host):
    cmd = host.run("yake-kubectl get crds")
    assert "clusterclasses.cluster.x-k8s.io" in cmd.stdout
    assert "clusters.cluster.x-k8s.io" in cmd.stdout
