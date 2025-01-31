#!/usr/bin/env bash

VERSION=v3.29.1

curl -o calico.yaml https://raw.githubusercontent.com/projectcalico/calico/refs/tags/$VERSION/manifests/calico.yaml
