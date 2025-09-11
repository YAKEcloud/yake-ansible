def test_helm_install_script(host):
    """Test if the helm script is properly installed."""
    f = host.file("/usr/local/bin/yake-helm")
    assert f.exists
    assert not f.is_directory
    assert f.mode == 0o755
    assert "#!/usr/bin/env bash" in f.content_string


def test_helm_install_container(host):
    """Test if the helm container is running."""
    container_name = "helm"
    container = host.docker(container_name)
    assert container.is_running


def test_helm_version_command(host):
    """Test if helm can execute version command."""
    cmd = host.run("yake-helm version --short")
    assert cmd.rc == 0
    assert "v" in cmd.stdout  # Version should contain a v prefix


def test_helm_help_command(host):
    """Test if helm can execute generic help commands."""
    cmd = host.run("yake-helm help")
    assert cmd.rc == 0
    assert "The Kubernetes package manager" in cmd.stdout


def test_helm_repo_commands(host):
    """Test if helm can execute repo commands."""
    # List repos
    cmd = host.run("yake-helm repo list")
    assert cmd.rc == 0

    # Try to add a repo (might already exist, so check for specific error)
    cmd = host.run("yake-helm repo add stable https://charts.helm.sh/stable")
    assert cmd.rc == 0 or "already exists" in cmd.stderr


def test_helm_kubeconfig_passthrough(host):
    """Test if KUBECONFIG environment variable is passed correctly."""
    # Check if the script passes KUBECONFIG to the container
    cmd = host.run("KUBECONFIG=/path/to/test yake-helm env")
    assert cmd.rc == 0
    # This should show the KUBECONFIG environment variable that was passed
    assert "KUBECONFIG=/path/to/test" in cmd.stdout
