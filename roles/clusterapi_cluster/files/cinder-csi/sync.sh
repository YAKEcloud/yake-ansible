#!/usr/bin/env bash

VERSION=v1.31.2

for file in cinder-csi-controllerplugin-rbac.yaml cinder-csi-controllerplugin.yaml cinder-csi-nodeplugin-rbac.yaml cinder-csi-nodeplugin.yaml csi-cinder-driver.yaml; do
    curl -o $file https://raw.githubusercontent.com/kubernetes/cloud-provider-openstack/refs/tags/$VERSION/manifests/cinder-csi-plugin/$file
done
