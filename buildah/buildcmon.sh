#!/usr/bin/bash

# use buildah to create a container holding the cmon tool
# started with podman run --interactive --tty --net=host -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 localhost/cmon:testing
#
# setting up the alias
# alias cmon="podman run --interactive --tty --net=host -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 --entrypoint='/cmon.py' localhost/cmon:testing "
# this allows you to use the container with parameters like this cmon -a or cmon -a -i
#
# with the ceph cli integration
# alias cmon='podman run --interactive --tty --net=host -v /home/paul/etc_ceph:/etc/ceph:ro,z -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 --entrypoint='\''/cmon.py'\'' localhost/cmon:devel'
#
if [ ! -z "$1" ]; then
  TAG=$1
else
  TAG='latest'
fi

echo "Build Alpine Linux image with the tag: $TAG"

IMAGE="alpine:edge"

container=$(buildah from $IMAGE)
buildah run $container apk add bash
buildah run $container apk add python3
buildah run $container apk add py3-yaml
buildah run $container apk add py3-requests
buildah run $container apk add py3-setuptools
buildah run $container apk add py3-urwid --repository http://dl-cdn.alpinelinux.org/alpine/edge/community/
buildah run $container apk add ceph-common --repository http://dl-cdn.alpinelinux.org/alpine/edge/community/
buildah run $container apk add py3-humanize --repository http://dl-cdn.alpinelinux.org/alpine/edge/testing/

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
buildah commit --format docker --squash $container cmon:$TAG
