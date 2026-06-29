# 从华为SRW拉去镜像

```bash
podman pull \
swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/memgraph/memgraph-mage:3.10.1
```

# 创建数据目录挂载

```bash
podman volume create memgraph-data
```

# 启动命令


```bash
podman run -d \
  --name memgraph \
  -p 17687:7687 \
  -p 17444:7444 \
  -v memgraph-data:/var/lib/memgraph \
  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/memgraph/memgraph-mage:3.10.1
```

# 验证数据库是否正常

```bash
podman exec -it memgraph mgconsole
```

# 推荐安装 Memgraph Lab（图形界面）

```bash
podman run -d \
  --name memgraph-lab \
  -p 3000:3000 \
  docker.io/memgraph/lab
```