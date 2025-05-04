# Docker镜像同步工具

这是一个自动化工具，用于将公共Docker镜像同步到你的私有Docker仓库。使用GitHub Actions每日定时执行，同时支持代码提交触发。

[English](./Readme-EN.md)

## 功能特点

- 🔄 自动同步指定的Docker镜像
- ⏰ 每日定时执行（UTC时间）
- 🚀 支持手动触发和代码提交触发
- 🔒 使用GitHub Secrets安全存储认证信息
- 📝 支持自定义目标镜像名称
- 🖥️ 支持指定平台架构

## 配置文件格式

在项目根目录创建 `sync-config.yaml` 文件：

```yaml
images:
  - source: kasmweb/nginx:1.25.3
    platform: linux/arm64
  - source: postgres:15
    target: a-postgres:15
    platform: linux/amd64
  - source: allanpk716/chinesesubfinder
  - source: linuxserver/jackett
  - source: diluka/nas-tools:2.9.1
```

字段说明：
- `source`: 源镜像地址（必填）
- `target`: 目标镜像名称（可选，默认使用源镜像名称）
- `platform`: 指定平台架构（可选，默认使用当前系统架构）

## 使用步骤

### 1. Fork本仓库

点击右上角的Fork按钮，将仓库Fork到你的GitHub账号下。

### 2. 配置GitHub Secrets

在你的仓库设置中添加以下Secrets：

- `TARGET_REGISTRY`: 目标Docker仓库地址（例如：`registry.example.com`）
- `TARGET_NAMESPACE`: 目标命名空间（例如：`myproject`）
- `REGISTRY_USERNAME`: Docker仓库用户名
- `REGISTRY_PASSWORD`: Docker仓库密码

### 3. 修改配置文件

编辑 `sync-config.yaml` 文件，添加你需要同步的镜像列表。

### 4. 启用GitHub Actions

确保仓库的Actions功能已启用。同步任务将会：
- 每天UTC时间00:00自动执行
- 每次提交代码时执行
- 支持手动触发

## 项目结构

```
.
├── .github/
│   └── workflows/
│       └── sync-images.yml    # GitHub Actions工作流配置
├── scripts/
│   └── sync.py               # 镜像同步脚本
├── sync-config.yaml          # 镜像同步配置文件
├── requirements.txt          # Python依赖
└── README.md                 # 本文档
```

## 同步脚本工作原理

1. 读取 `sync-config.yaml` 配置文件
2. 登录到目标Docker仓库
3. 遍历镜像列表：
   - 拉取源镜像
   - 重新标记为目标镜像名称
   - 推送到目标仓库
4. 记录同步结果

## 手动触发同步

1. 进入仓库的Actions页面
2. 选择"Sync Docker Images"工作流
3. 点击"Run workflow"按钮
4. 选择分支并运行

## 日志和监控

- 同步日志可在GitHub Actions的运行记录中查看
- 失败的同步任务会在Actions页面显示红色标记
- 建议设置GitHub通知以接收同步失败的提醒

## 常见问题

### Q: 如何处理私有源镜像？
A: 可以在GitHub Secrets中添加 `SOURCE_REGISTRY_USERNAME` 和 `SOURCE_REGISTRY_PASSWORD`，并在脚本中添加源仓库登录逻辑。

### Q: 如何修改同步时间？
A: 编辑 `.github/workflows/sync-images.yml` 文件中的cron表达式。

### Q: 同步失败怎么办？
A: 检查Actions日志，常见原因包括：
- 网络问题
- 认证失败
- 镜像不存在
- 磁盘空间不足

## 贡献指南

欢迎提交Issue和Pull Request来改进这个工具！

## 许可证

MIT License
