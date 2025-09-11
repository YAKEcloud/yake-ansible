# yake-ansible

At the moment we only support Openstack as infrastructure and for DNS. Get in contact with us, if you need another Cloud.
But it is possible to write your own cloudprofiles for AWS, Azure, or GCP (we have already implemented the extensions for this as an option).

## Installation

```
virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Usage

```
ansible-playbook -i localhost, -c local site.yml
```

### Single steps

```
ansible-playbook -i localhost, -c local kubectl-install.yml
ansible-playbook -i localhost, -c local helm-install.yml
ansible-playbook -i localhost, -c local clusterctl-install.yml
ansible-playbook -i localhost, -c local kind-install.yml
ansible-playbook -i localhost, -c local kind-cluster.yml
ansible-playbook -i localhost, -c local clusterapi-install.yml
ansible-playbook -i localhost, -c local clusterapi-cluster.yml
ansible-playbook -i localhost, -c local gardener-operator.yml
```

### Accessing the Cluster API cluster

```
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
yake-kubectl get nodes
```

### Accessing the Garden cluster

```
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
yake-kubectl get nodes
```

### Patch/Upgrade
If you want to patch/upgrade your gardener, just run the playbook once again and set the variable `gardener_operator_version` to the next version you like. Your gardener will be patched/upgraded to this version.

### Cleanup

```
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl delete cluster garden
./.local/yake-kind delete cluster --name clusterapi
docker rm -f $(docker ps -qa)
sudo rm -rf /var/lib/yake/
```
