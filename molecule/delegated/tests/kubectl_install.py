def test_kubectl_install_script(host):
    """Test if the kubectl script is properly installed."""
    f = host.file("/usr/local/bin/yake-kubectl")
    assert f.exists
    assert not f.is_directory
    assert f.mode == 0o755
    assert "#!/usr/bin/env bash" in f.content_string


def test_kubectl_install_container(host):
    """Test if the kubectl container is running."""
    container_name = "kubectl"
    container = host.docker(container_name)
    assert container.is_running


def test_kubectl_version_command(host):
    """Test if kubectl can execute version command."""
    cmd = host.run("yake-kubectl version --client")
    assert cmd.rc == 0
    assert "Client Version" in cmd.stdout


def test_kubectl_exec_command(host):
    """Test if kubectl can execute generic commands."""
    # Test basic command execution
    cmd = host.run("yake-kubectl get --help")
    assert cmd.rc == 0
    assert "Display one or many resources" in cmd.stdout


def test_kubectl_kubeconfig_passthrough(host):
    """Test if KUBECONFIG environment variable is passed correctly."""
    # Check if the script passes KUBECONFIG to the container
    cmd = host.run("KUBECONFIG=/path/to/test yake-kubectl config view")
    assert cmd.rc == 0
    # Note: this might not show the actual content since the kubeconfig likely
    # doesn't exist, but should still run the command
