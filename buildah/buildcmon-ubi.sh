#!/usr/bin/bash

# use buildah to create a container holding the cmon tool
# started with podman run --interactive --tty --net=host -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 localhost/cmon:testing
#
# setting up the alias
# alias cmon="podman run --interactive --tty --net=host -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 --entrypoint='/cmon.py' localhost/cmon:testing "
# this allows you to use the container with parameters like this cmon -a or cmon -a -i
#
# Ref: https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/html-single/building_running_and_managing_containers/index
#
# Run this on a system that has the baseos and appstream repos already enabled, to ensure they are available
# to microdnf in the ubi container
#
if [ ! -z "$1" ]; then
  TAG=$1
else
  TAG='latest'
fi

echo "Build RHEL UBI image with the tag: $TAG"

IMAGE="registry.access.redhat.com/ubi8/ubi-minimal:latest"

container=$(buildah from $IMAGE)
buildah run $container microdnf install bash
buildah run $container microdnf install -y python3
buildah run $container microdnf install -y python3-pyyaml
buildah run $container microdnf install -y python3-requests
buildah run $container microdnf install -y python3-setuptools
buildah run $container microdnf install -y python3-urwid
buildah run $container microdnf install -y python3-humanize

buildah run $container mkdir -p /cmon

buildah copy $container ../cmon /cmon
buildah copy $container ../cmon.py /cmon.py

buildah run $container chmod ug+x /cmon.py

# entrypoint
#buildah config --entrypoint "/usr/bin/python3 /cmon.py" $container

# finalize
buildah config --label maintainer="Paul Cuzner <pcuzner@redhat.com>" $container
buildah config --label description="cmon ceph monitor applicaion" $container
buildah config --label summary="CLI based ceph monitoring application" $container
buildah commit --format docker --squash $container cmon-ubi:$TAG
