#!/usr/bin/env python3
"""
Docker镜像同步脚本
用于将公共Docker镜像同步到私有仓库

特性:
- 基于 digest 比较,仅在内容变化时同步
- 支持 skopeo(免 pull)加速检测
- 支持多架构 manifest
- 支持强制同步(force)
- 自动处理 latest 等移动 tag
- 自动登录私有仓库
"""

import os
import sys
import json
import yaml
import shutil
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ---------- 默认移动 tag ----------
DEFAULT_MOVING_TAGS = {
    "latest", "stable", "edge", "dev", "main",
    "master", "nightly", "beta", "alpha", "canary",
}


# ---------- 配置数据类 ----------
@dataclass
class ImageConfig:
    """单个镜像配置"""
    source: str
    target: Optional[str] = None
    platform: Optional[str] = None
    force: bool = False

    def get_target_image(self, target_registry: str, target_namespace: str) -> str:
        """获取目标镜像全名"""
        if self.target:
            image_name = self.target
        else:
            image_name = self.source.split('/')[-1]
        return f"{target_registry}/{target_namespace}/{image_name}"


@dataclass
class GlobalSettings:
    """全局设置"""
    force_moving_tags: bool = False
    moving_tags: set = field(default_factory=lambda: set(DEFAULT_MOVING_TAGS))
    target_username: Optional[str] = None
    target_password: Optional[str] = None


# ---------- 工具函数 ----------
def get_image_tag(image_ref: str) -> str:
    """
    从镜像引用中解析 tag。
    处理形如:
      nginx               -> latest
      nginx:1.25          -> 1.25
      registry.io/a/b:tag -> tag
      registry.io:5000/a  -> latest
    """
    # 去掉 digest 部分
    if "@" in image_ref:
        image_ref = image_ref.split("@")[0]
    
    # 分离最后一个 / 之后的 name[:tag] 部分
    last_slash = image_ref.rfind("/")
    name_part = image_ref[last_slash + 1:] if last_slash != -1 else image_ref
    
    if ":" in name_part:
        return name_part.split(":")[-1]
    return "latest"


def is_moving_tag(image_ref: str, moving_tags: set) -> bool:
    """判断镜像是否使用移动 tag"""
    return get_image_tag(image_ref).lower() in {t.lower() for t in moving_tags}


def has_skopeo() -> bool:
    """检查系统是否安装 skopeo"""
    return shutil.which("skopeo") is not None


# ---------- 主类 ----------
class DockerImageSync:
    """Docker镜像同步类"""

    def __init__(self, config_file: str = "sync-config.yaml"):
        self.config_file = config_file
        self.target_registry = os.environ.get("TARGET_REGISTRY")
        self.target_namespace = os.environ.get("TARGET_NAMESPACE")
        self.results: List[Dict] = []
        self.settings = GlobalSettings()
        self.use_skopeo = has_skopeo()

        if not self.target_registry or not self.target_namespace:
            raise ValueError(
                "TARGET_REGISTRY and TARGET_NAMESPACE environment variables must be set"
            )

        logger.info(
            f"Target: {self.target_registry}/{self.target_namespace} | "
            f"skopeo available: {self.use_skopeo}"
        )

    # ---------- 配置加载 ----------
    def load_config(self) -> Tuple[GlobalSettings, List[ImageConfig]]:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            raise

        # 解析全局设置
        settings_cfg = config.get('settings', {}) or {}
        settings = GlobalSettings(
            force_moving_tags=bool(settings_cfg.get('force_moving_tags', False)),
            moving_tags=set(settings_cfg.get('moving_tags', DEFAULT_MOVING_TAGS)),
            target_username=settings_cfg.get('target_username')
                or os.environ.get("TARGET_USERNAME"),
            target_password=settings_cfg.get('target_password')
                or os.environ.get("TARGET_PASSWORD"),
        )
        self.settings = settings

        # 解析镜像列表
        images: List[ImageConfig] = []
        for item in config.get('images', []) or []:
            # 兼容简单写法: - nginx:latest
            if isinstance(item, str):
                images.append(ImageConfig(source=item))
            elif isinstance(item, dict):
                # 兼容 dict 里多出来的字段
                allowed = {"source", "target", "platform", "force"}
                filtered = {k: v for k, v in item.items() if k in allowed}
                images.append(ImageConfig(**filtered))
            else:
                logger.warning(f"Skip invalid image config: {item}")

        logger.info(f"Loaded {len(images)} image configurations")
        return settings, images

    # ---------- 执行命令 ----------
    def run_command(
        self, command: List[str], check: bool = True
    ) -> Tuple[bool, str, str]:
        """执行命令,返回 (成功, stdout, stderr)"""
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            if check and result.returncode != 0:
                logger.error(f"Command failed: {' '.join(command)}")
                logger.error(f"Error output: {result.stderr.strip()}")
                return False, result.stdout, result.stderr
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            logger.error(f"Command exception: {' '.join(command)} -> {e}")
            return False, "", str(e)

    # ---------- 登录 ----------
    def login(self) -> bool:
        """登录目标仓库(如果提供了凭据)"""
        if not self.settings.target_username or not self.settings.target_password:
            logger.info("No target credentials provided, skip login")
            return True

        logger.info(f"Logging in to {self.target_registry}...")
        command = [
            "docker", "login", self.target_registry,
            "-u", self.settings.target_username,
            "--password-stdin",
        ]
        try:
            result = subprocess.run(
                command,
                input=self.settings.target_password,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.error(f"Login failed: {result.stderr.strip()}")
                return False
            logger.info("Login successful")
            return True
        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    # ---------- digest 获取 ----------
    def get_remote_digest(self, image: str) -> Optional[str]:
        """
        获取远程镜像的 digest。
        优先使用 skopeo(支持免 pull、多架构),否则回退到 docker manifest。
        返回 manifest digest(对于多架构是 manifest list 的 digest)。
        """
        # 优先 skopeo
        if self.use_skopeo:
            cmd = [
                "skopeo", "inspect",
                f"docker://{image}",
                "--format", "{{.Digest}}",
            ]
            ok, stdout, _ = self.run_command(cmd, check=False)
            if ok and stdout.strip():
                return stdout.strip()

        # 回退: docker manifest inspect --verbose
        cmd = ["docker", "manifest", "inspect", "--verbose", image]
        ok, stdout, _ = self.run_command(cmd, check=False)
        if not ok:
            return None
        try:
            data = json.loads(stdout)
            # 单架构: {"Descriptor": {"digest": "sha256:..."}}
            # 多架构: [{...}, {...}]
            if isinstance(data, dict):
                desc = data.get("Descriptor") or {}
                return desc.get("digest") or data.get("digest")
            if isinstance(data, list) and data:
                # 多架构场景,取第一个(顶层 manifest list 的 digest
                # 通常需要另行获取,这里退化为取第一个子 manifest)
                first = data[0]
                desc = first.get("Descriptor") or {}
                return desc.get("digest") or first.get("digest")
        except Exception as e:
            logger.debug(f"Failed to parse manifest for {image}: {e}")
        return None

    def get_local_digest(self, image: str) -> Optional[str]:
        """获取本地已 pull 镜像的 digest(RepoDigests)"""
        cmd = [
            "docker", "inspect",
            "--format", "{{index .RepoDigests 0}}",
            image,
        ]
        ok, stdout, _ = self.run_command(cmd, check=False)
        if not ok or not stdout.strip():
            return None
        # 形如 nginx@sha256:xxxx
        if "@" in stdout.strip():
            return stdout.strip().split("@", 1)[1]
        return None

    def get_source_digest(self, image: str) -> Optional[str]:
        """
        获取源镜像的 digest。
        优先 skopeo(免 pull),否则需要先 pull 再用 docker inspect。
        """
        if self.use_skopeo:
            cmd = [
                "skopeo", "inspect",
                f"docker://{image}",
                "--format", "{{.Digest}}",
            ]
            ok, stdout, _ = self.run_command(cmd, check=False)
            if ok and stdout.strip():
                return stdout.strip()
        return None

    # ---------- 判断是否需要同步 ----------
    def should_sync(self, image_config: ImageConfig, target_image: str) -> Tuple[bool, str]:
        """
        判断是否需要同步。
        返回 (是否需要同步, 原因说明)
        """
        # 1. force 优先级最高
        if image_config.force:
            return True, "force=true, always sync"

        # 2. 目标不存在 -> 需要同步
        remote_digest = self.get_remote_digest(target_image)
        if remote_digest is None:
            return True, "target image not found in remote"

        # 3. 移动 tag + 全局强制移动 tag 策略
        if (
            self.settings.force_moving_tags
            and is_moving_tag(image_config.source, self.settings.moving_tags)
        ):
            return True, f"moving tag '{get_image_tag(image_config.source)}' always sync"

        # 4. 获取源 digest 进行比较
        source_digest = self.get_source_digest(image_config.source)
        if source_digest is None:
            # skopeo 不可用时,只能保守同步
            if not self.use_skopeo:
                return True, "skopeo unavailable, cannot compare digest, sync to be safe"
            return True, "cannot fetch source digest"

        if source_digest == remote_digest:
            return False, f"digest unchanged ({source_digest[:19]}...)"

        return True, f"digest changed: {remote_digest[:19]}... -> {source_digest[:19]}..."

    # ---------- 镜像操作 ----------
    def pull_image(self, source: str, platform: Optional[str] = None) -> bool:
        """拉取源镜像"""
        logger.info(f"Pulling image: {source}" + (f" [{platform}]" if platform else ""))
        command = ["docker", "pull"]
        if platform:
            command.extend(["--platform", platform])
        command.append(source)
        return self.run_command(command)[0]

    def tag_image(self, source: str, target: str) -> bool:
        """标记镜像"""
        logger.info(f"Tagging image: {source} -> {target}")
        return self.run_command(["docker", "tag", source, target])[0]

    def push_image(self, target: str, platform: Optional[str] = None) -> bool:
        """
        推送镜像到目标仓库。
        注意: docker push 不支持 --platform,平台在 pull 阶段决定。
        """
        logger.info(f"Pushing image: {target}")
        return self.run_command(["docker", "push", target])[0]

    # ---------- 同步单个镜像 ----------
    def sync_image(self, image_config: ImageConfig) -> Dict:
        """同步单个镜像"""
        start_time = datetime.now()
        target_image = image_config.get_target_image(
            self.target_registry, self.target_namespace
        )

        result = {
            "source": image_config.source,
            "target": target_image,
            "platform": image_config.platform,
            "force": image_config.force,
            "start_time": start_time.isoformat(),
            "end_time": None,
            "duration": None,
            "success": False,
            "skipped": False,
            "reason": None,
            "error": None,
        }

        try:
            # 1. 判断是否需要同步
            need_sync, reason = self.should_sync(image_config, target_image)
            result["reason"] = reason
            logger.info(f"[{image_config.source}] {reason}")

            if not need_sync:
                result["success"] = True
                result["skipped"] = True
                return result

            # 2. 拉取源镜像
            if not self.pull_image(image_config.source, image_config.platform):
                raise Exception("Failed to pull source image")

            # 3. 标记
            if not self.tag_image(image_config.source, target_image):
                raise Exception("Failed to tag image")

            # 4. 推送
            if not self.push_image(target_image, image_config.platform):
                raise Exception("Failed to push image")

            result["success"] = True
            logger.info(f"Successfully synced: {image_config.source}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Failed to sync {image_config.source}: {e}")

        finally:
            end_time = datetime.now()
            result["end_time"] = end_time.isoformat()
            result["duration"] = round((end_time - start_time).total_seconds(), 2)

        return result

    # ---------- 同步全部 ----------
    def sync_all(self):
        """同步所有镜像"""
        try:
            settings, images = self.load_config()

            # 登录(如果需要)
            if not self.login():
                logger.error("Login failed, abort")
                sys.exit(1)

            for image_config in images:
                result = self.sync_image(image_config)
                self.results.append(result)

            # 保存结果
            self.save_results()

            # 统计
            successful = sum(1 for r in self.results if r["success"])
            failed = sum(1 for r in self.results if not r["success"])
            skipped = sum(1 for r in self.results if r.get("skipped", False))
            synced = successful - skipped

            logger.info(
                f"Sync completed: {successful}/{len(self.results)} successful "
                f"({synced} synced, {skipped} skipped), {failed} failed"
            )

            if failed > 0:
                sys.exit(1)

        except Exception as e:
            logger.error(f"Sync process failed: {e}")
            sys.exit(1)

    # ---------- 保存结果 ----------
    def save_results(self):
        """保存同步结果(带时间戳,保留历史)"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = os.environ.get("SYNC_RESULT_DIR", "sync-results")
        os.makedirs(output_dir, exist_ok=True)

        # 带时间戳的历史文件
        output_file = os.path.join(output_dir, f"sync-results-{timestamp}.json")
        try:
            with open(output_file, "w") as f:
                json.dump(
                    {
                        "timestamp": timestamp,
                        "target_registry": self.target_registry,
                        "target_namespace": self.target_namespace,
                        "results": self.results,
                    },
                    f,
                    indent=2,
                )
            logger.info(f"Results saved to {output_file}")

            # 同时更新 latest 软链/副本,方便消费
            latest_file = os.path.join(output_dir, "sync-results-latest.json")
            with open(latest_file, "w") as f:
                json.dump(self.results, f, indent=2)
            logger.info(f"Latest results also at {latest_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")


# ---------- 入口 ----------
def main():
    """主函数"""
    config_file = os.environ.get("SYNC_CONFIG", "sync-config.yaml")
    sync = DockerImageSync(config_file=config_file)
    sync.sync_all()


if __name__ == "__main__":
    main()
