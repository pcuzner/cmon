# cmon

## Introduction
**cmon** is a light-weight monitoring tool for [Ceph](https://ceph.io/en/) that runs in your console window. It exploits the metrics and state information that Ceph already provides to Prometheus, so all it needs is access to the http endpoints of the mgr/prometheus module...no complex client code and no changes to Ceph needed! In addition, cmon can also integrate with Prometheus to show active alerts and performance data (last 15 mins) to give you a more holistic view of your Ceph cluster's health, configuration and performance.

## What do I get for my trouble?
Here's an example of cmon running on a small test cluster
&nbsp;
![cmon demo](media/cmon-demo-2021-07.gif)
&nbsp;
## TL;DR
Here's a quick way of trying out the tool
1. grab the container image
```
podman pull docker.io/pcuzner/cmon:latest
```
2. create an command alias that will run the image and pass in the URLs for ceph mgr and prometheus (docker user? Just replace podman!)
```
alias cmon="podman run --interactive --tty --net=host -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 --entrypoint='/cmon.py' docker.io/pcuzner/cmon:latest"
```

3. run the command.
```
cmon
```
Once it launches, '**h**' shows you a help page which lists the other keys that toggle displays on and off.
&nbsp;

## Features
The idea around the tool is to provide a quick and easy dashboard for a Ceph cluster, that can run anywhere with little or no dependencies. Here's some of cmon's features;

- integrated help - *just press 'h' to show the help page*
- optional panels can be toggled on or off
- config file and environment variables can be used to set default panels and connection URLs
- inventory overview and overall ceph daemon state
- IO load graph (IOPS and throughput) sourced from Prometheus
- currently active alerts, also sourced from Prometheus
- capacity status, with compression yield
- pool configuration, capacity and performance breakdown
- top 10 rbd's by IOPS (needs rbd_stats_pools option set in mgr/prometheus)
- RGW performance, per instance (GETs/PUTs and bandwidth)
&nbsp;

## Installation
There are a several methods for installing cmon.

1. Run it from a container
   - ```docker pull docker.io/pcuzner/cmon:latest```


2. Install it from source, and install
   - grab this archive
   - run setup.py (TODO)

3. run locally from a directory
   - grab the source
   - install the pre-requisites
   - run cmon.py

&nbsp;
## Usage

### Command line options

```
usage: cmon.py [-h] [--log-level {info,debug,error}] [--log-file LOG_FILE] [--ceph-url CEPH_URL] [--prometheus-url PROMETHEUS_URL] [--alertmanager-url ALERTMANAGER_URL] [--refresh-interval {5,10,15}]
               [--config-file CONFIG_FILE] [-i] [-a] [-p] [-r] [-g]

optional arguments:
  -h, --help            show this help message and exit
  --log-level {info,debug,error}
                        logging mode for diagnostics
  --log-file LOG_FILE   filename for logging
  --ceph-url CEPH_URL   URL(s) of the ceph endpoints (e.g. http://<hostname>:<port>/metrics)
  --prometheus-url PROMETHEUS_URL
                        URL of the Prometheus server endpoint (hostname:port)
  --alertmanager-url ALERTMANAGER_URL
                        URL of an alertmanager endpoint (hostname:port)
  --refresh-interval {5,10,15}
                        Should be the same as the mgr/prometheus module's scrape_interval setting
  --config-file CONFIG_FILE
                        config file in yaml format for for default
  -i, --ioload          show I/O load panel
  -a, --alerts          show Prometheus Alerts
  -p, --pools           show Pool information
  -r, --rbds            show RBD performance information (if pool enabled in prometheus)
  -g, --rgws            show RGW performance information
```

### Configuration file (yaml)
In addition to runtime settings, cmon also looks for a cmon.yaml file which would describe how to run. An example is shown below

```
---
ceph_url: http://192.168.122.92:9283/metrics
prometheus_url: http://192.168.122.92:9095

#panel_ioload: true
```

### Environment Variables
In addition to the configuration file and run time options, cmon also looks for environment variables to apply. These variables match the settings you can apply within the configuration file.

Environment variables are most typically used when running the cmon as a container.

### Refresh Interval
Since cmon relies on data sourced from or for Prometheus, you need to use the same refresh interval in cmon that Ceph's mgr/prometheus module uses. The refresh-interval is a simple parameter that you can add on the invocation of cmon, or include in a config file...but by default to Ceph's default value. You can check the interval that your prometheus module is using with;
```
# ceph config get mgr mgr/prometheus/scrape_interval
15.000000
```


### Running cmon as a container
Instead of installing dependencies or an rpm, you can run cmon from a container..as long as you have a container runtime :P

Here's an example that picks up mgr and prometheus from 192.168.122.92
```
alias cmon="podman run --interactive --tty --net=host -e TERM -e CEPH_URL=http://192.168.122.92:9283/metrics -e PROMETHEUS_URL=http://192.168.122.92:9095 --entrypoint='/cmon.py' pcuzner/cmon:latest"
```

### Container
The smallest container image for cmon is based on Alpine, but the buildah folder contains scripts to build cmon for other base images.

Here's a comparison of the images sizes<sup>1</sup>
| Base Image | Size |
| --------- | ----- |
| Alpine | 69 MB |
| RH-UBI-8 | 152 MB |
| Ubuntu LTS | 157 MB |
| CentOS 8 | 261 MB |

<sup>1</sup> You can probably shrink the RH/CentOS/Ubuntu images with more work - this is just 'out-of-the-box' sizings.

## Troubleshooting
1. *"cmon fails to start. I get 'Unable to build the metrics from mgr/prometheus...'"*
   cmon relies on the mgr/prometheus module - is it enabled? ```ceph mgr module ls``` to check, and ```ceph mgr module enable prometheus``` to enable.
1. *"My graphs show a saw-tooth pattern with workload appearing to stop every few seconds...what's that about?"*
  Check your refresh-interval is correct - this pattern of regular lapses in data is normally when you're refresh-interval is smaller than the interval used in mgr/prometheus and the prometheus scrape job.
2. *"My IO load panel just says prometheus returned no data, what do I do?"*
   This indicates that the mgr/prometheus endpoint is not being scraped, so there is no ceph_* related metrics for the query to return. Check that port 9283 on the mgr is listening, and that the prometheus configuration has a job to scrape from ceph configured correctly (IP/hostname and port are correct?)


## Known Issues
1. The widgets in the UI require a minimum width. If you resize your console window to be too small, the app will shutdown since it's no longer able to display content.


## Feature Wishlist
- add an about (?) panel to overlay release, and compatibility matrix (what panels work with what release)
- enable cmon to handle multiple clusters, and switch between them
  * change the configuration file format. Allow a list of servers and introduce a nickname for selection
  * Add a pulldown on the header widget to provide quick switch across clusters
  * Add an ALL nickname to show a different multi-cluster aggregation of statistics - activity, capacity, health
- enable the container to use a token in the header of the prometheus calls to enable the tool to deal with proxied prometheus instances, like those inside OCP/kubernetes
- consider predetermined layouts so when a component is toggled the whole layout changes - not sure about this one..
- add 'h' Host panel to show a host breakdown - ceph components and current cpu/ram load by host
- add 'o' OSD panel (overlay) to detail all OSDs in a table, with a summary panel embedded
- switch to alertmanager url for the alerts table so we can see alerts that are silenced
- Singlestat panel to indicate when recovery/backfill is active?



## Maybe's
- consider a metric history based on the delta values as an alternative to the prometheus query

