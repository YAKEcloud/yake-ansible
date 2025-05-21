def test_flux_install_script(host):
    """Test if the flux script is properly installed."""
    f = host.file("/usr/local/bin/yake-flux")
    assert f.exists
    assert not f.is_directory
    assert f.mode == 0o755
    assert "#!/usr/bin/env bash" in f.content_string


def test_flux_install_container(host):
    """Test if the flux container is running."""
    container_name = "flux"
    container = host.docker(container_name)
    assert container.is_running


def test_flux_version_command(host):
    """Test if flux can execute version command."""
    cmd = host.run("yake-flux --version")
    assert cmd.rc == 0
    assert "flux" in cmd.stdout


def test_flux_help_command(host):
    """Test if flux can execute help commands."""
    cmd = host.run("yake-flux help")
    assert cmd.rc == 0
    assert "Available Commands:" in cmd.stdout


def test_flux_check_command(host):
    """Test if flux can execute check command."""
    cmd = host.run("yake-flux check --pre")
    assert cmd.rc == 0


def test_flux_kubeconfig_passthrough(host):
    """Test if KUBECONFIG environment variable is passed correctly."""
    # Check if the script passes KUBECONFIG to the container
    cmd = host.run("KUBECONFIG=/path/to/test yake-flux env")
    assert cmd.rc == 0
    # This should show the KUBECONFIG environment variable that was passed
    assert "KUBECONFIG=/path/to/test" in cmd.stdout


def test_flux_cli_capabilities(host):
    """Test if flux cli has expected capabilities."""
    # Test some common flux commands
    commands_to_test = [
        "yake-flux install --help",
        "yake-flux bootstrap --help",
        "yake-flux create --help",
        "yake-flux get --help",
        "yake-flux reconcile --help",
    ]

    for command in commands_to_test:
        cmd = host.run(command)
        assert cmd.rc == 0
