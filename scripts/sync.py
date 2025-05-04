#!/usr/bin/env python3
"""
Docker镜像同步脚本
用于将公共Docker镜像同步到私有仓库
"""

import os
import sys
import json
import yaml
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

@dataclass
class ImageConfig:
    """镜像配置数据类"""
    source: str
    target: Optional[str] = None
    platform: Optional[str] = None

    def get_target_image(self, target_registry: str, target_namespace: str) -> str:
        """获取目标镜像全名"""
        if self.target:
            # 如果指定了目标名称，使用指定的名称
            image_name = self.target
        else:
            # 否则使用源镜像名称
            image_name = self.source.split('/')[-1]
        
        return f"{target_registry}/{target_namespace}/{image_name}"

class DockerImageSync:
    """Docker镜像同步类"""
    
    def __init__(self, config_file: str = "sync-config.yaml"):
        self.config_file = config_file
        self.target_registry = os.environ.get("TARGET_REGISTRY")
        self.target_namespace = os.environ.get("TARGET_NAMESPACE")
        self.results = []
        
        if not self.target_registry or not self.target_namespace:
            raise ValueError("TARGET_REGISTRY and TARGET_NAMESPACE environment variables must be set")
    
    def load_config(self) -> List[ImageConfig]:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            images = []
            for image_config in config.get('images', []):
                images.append(ImageConfig(**image_config))
            
            logger.info(f"Loaded {len(images)} image configurations")
            return images
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            raise
    
    def run_docker_command(self, command: List[str]) -> bool:
        """执行Docker命令"""
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            logger.debug(f"Command output: {result.stdout}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(command)}")
            logger.error(f"Error output: {e.stderr}")
            return False
    
    def pull_image(self, source: str, platform: Optional[str] = None) -> bool:
        """拉取源镜像"""
        logger.info(f"Pulling image: {source}")
        command = ["docker", "pull", source]
        
        if platform:
            command.extend(["--platform", platform])
        
        return self.run_docker_command(command)
    
    def tag_image(self, source: str, target: str) -> bool:
        """标记镜像"""
        logger.info(f"Tagging image: {source} -> {target}")
        command = ["docker", "tag", source, target]
        return self.run_docker_command(command)
    
    def push_image(self, target: str) -> bool:
        """推送镜像到目标仓库"""
        logger.info(f"Pushing image: {target}")
        command = ["docker", "push", target]
        return self.run_docker_command(command)
    
    def check_remote_image_exists(self, image: str) -> bool:
        """检查远程仓库是否已存在镜像"""
        logger.info(f"Checking if image exists in remote: {image}")
        command = ["docker", "manifest", "inspect", image]
        
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Image already exists: {image}")
                return True
            else:
                logger.info(f"Image not found: {image}")
                return False
        except Exception as e:
            logger.warning(f"Failed to check remote image: {e}")
            return False
    
    def sync_image(self, image_config: ImageConfig) -> Dict[str, any]:
        """同步单个镜像"""
        start_time = datetime.now()
        result = {
            "source": image_config.source,
            "target": image_config.get_target_image(self.target_registry, self.target_namespace),
            "platform": image_config.platform,
            "start_time": start_time.isoformat(),
            "success": False,
            "error": None,
            "skipped": False
        }
        
        try:
            # 检查目标镜像是否已存在
            if self.check_remote_image_exists(result["target"]):
                result["success"] = True
                result["skipped"] = True
                result["message"] = "Image already exists in target registry"
                logger.info(f"Skipped syncing {image_config.source}: already exists in target")
                return result
            
            # 拉取源镜像
            if not self.pull_image(image_config.source, image_config.platform):
                raise Exception("Failed to pull source image")
            
            # 标记镜像
            if not self.tag_image(image_config.source, result["target"]):
                raise Exception("Failed to tag image")
            
            # 推送镜像
            if not self.push_image(result["target"]):
                raise Exception("Failed to push image")
            
            result["success"] = True
            logger.info(f"Successfully synced: {image_config.source}")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Failed to sync {image_config.source}: {e}")
        
        finally:
            end_time = datetime.now()
            result["end_time"] = end_time.isoformat()
            result["duration"] = (end_time - start_time).total_seconds()
        
        return result
    
    def sync_all(self):
        """同步所有镜像"""
        try:
            images = self.load_config()
            
            for image_config in images:
                result = self.sync_image(image_config)
                self.results.append(result)
            
            # 保存结果
            self.save_results()
            
            # 统计结果
            successful = sum(1 for r in self.results if r["success"])
            failed = sum(1 for r in self.results if not r["success"])
            skipped = sum(1 for r in self.results if r.get("skipped", False))
            
            logger.info(f"Sync completed: {successful} successful ({skipped} skipped), {failed} failed")
            
            if failed > 0:
                sys.exit(1)
                
        except Exception as e:
            logger.error(f"Sync process failed: {e}")
            sys.exit(1)
    
    def save_results(self):
        """保存同步结果"""
        try:
            with open("sync-results.json", "w") as f:
                json.dump(self.results, f, indent=2)
            logger.info("Results saved to sync-results.json")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

def main():
    """主函数"""
    sync = DockerImageSync()
    sync.sync_all()

if __name__ == "__main__":
    main()