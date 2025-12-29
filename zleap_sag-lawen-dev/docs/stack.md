# Stack

相关工具使用

---

### UV 包管理器

#### 虚拟环境管理

```bash
# 创建虚拟环境
uv venv                    # 创建 .venv 目录
uv venv myenv              # 创建指定名称的虚拟环境
uv venv --python 3.11      # 指定 Python 版本

# 激活虚拟环境
source .venv/bin/activate           # macOS/Linux
.venv\Scripts\activate              # Windows PowerShell
.venv\Scripts\activate.bat          # Windows CMD

# 停用虚拟环境
deactivate
```

#### 依赖安装

```bash
# 安装单个包
uv pip install requests
uv pip install "fastapi>=0.100.0"

# 从 requirements.txt 安装
uv pip install -r requirements.txt

# 从 pyproject.toml 安装
uv pip install -e .                 # 开发模式安装
uv pip install -e ".[dev]"          # 安装开发依赖
uv pip install -e ".[dev,test]"     # 安装多个可选依赖

# 使用 uv sync（推荐）
uv sync                    # 同步 pyproject.toml 的所有依赖
uv sync --all-extras       # 同步所有可选依赖
```

#### 依赖管理

```bash
# 列出已安装的包
uv pip list
uv pip list --format=json

# 显示包信息
uv pip show requests

# 冻结依赖
uv pip freeze > requirements.txt

# 卸载包
uv pip uninstall requests
uv pip uninstall -r requirements.txt

# 升级包
uv pip install --upgrade requests
uv pip install --upgrade-package requests
```

#### 项目初始化

```bash
# 初始化新项目
uv init myproject
cd myproject

# 添加依赖
uv add fastapi
uv add --dev pytest

# 移除依赖
uv remove fastapi
```

### 3.4 UV 最佳实践

#### 1. 使用 uv sync 管理依赖

```bash
# 不要使用
uv pip install -e ".[dev]"

# 推荐使用
uv sync --all-extras
```

优势：
- 自动生成 `uv.lock` 锁文件
- 确保所有环境依赖一致
- 更快的依赖解析

#### 2. 项目开发工作流

```bash
# 1. 克隆项目
git clone https://github.com/zleap-team/dataflow.git
cd dataflow

# 2. 创建虚拟环境
uv venv

# 3. 激活虚拟环境
source .venv/bin/activate  # macOS/Linux

# 4. 同步所有依赖（包括dev和api）
uv sync --all-extras

# 5. 运行应用
python -m dataflow
```

#### 3. 依赖锁定

```bash
# 生成锁文件
uv sync  # 自动生成 uv.lock

# 从锁文件安装（CI/CD）
uv sync --frozen  # 不更新 uv.lock
```

#### 4. 与 Docker 集成

**Dockerfile 优化**:

```dockerfile
FROM python:3.11-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock* ./

# 安装依赖（使用 uv 的系统模式）
RUN uv pip install --system -e ".[api]"

# 复制项目文件
COPY . .

CMD ["uvicorn", "dataflow.api.main:app", "--host", "0.0.0.0"]
```

#### 5. 加速技巧

```bash
# 使用国内镜像源
uv pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple requests

# 配置环境变量
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 并行安装（默认启用）
uv pip install requests pandas numpy  # 自动并行下载
```

### 3.5 常见问题排查

#### 问题 1: 权限错误

```bash
# 错误: Permission denied
# 解决: 使用 --user 或虚拟环境
uv pip install --user package_name
# 或
uv venv && source .venv/bin/activate
```

#### 问题 2: 找不到 uv 命令

```bash
# macOS/Linux
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Windows
# 添加到 PATH: C:\Users\YourName\.cargo\bin
```

#### 问题 3: Python 版本不匹配

```bash
# 指定 Python 版本
uv venv --python 3.11
uv venv --python /usr/bin/python3.11
```

#### 问题 4: 依赖冲突

```bash
# 查看详细信息
uv pip install package_name --verbose

# 强制重新解析
rm -rf .venv uv.lock
uv venv
uv sync
```

#### 问题 5: 网络超时

```bash
# 增加超时时间
uv pip install --timeout 300 package_name

# 使用镜像源
uv pip install --index-url https://mirrors.aliyun.com/pypi/simple/ package_name
```

### 3.6 UV vs 其他工具对比

```bash
# pip: 传统方式
pip install -r requirements.txt
# 时间: ~30s

# Poetry: 现代方式
poetry install
# 时间: ~15s

# uv: 极速方式
uv sync
# 时间: ~2s ⚡
```

### 3.7 进阶用法

#### 批量更新依赖

```bash
# 更新所有包
uv pip list --outdated
uv pip install --upgrade-all

# 更新特定包
uv pip install --upgrade fastapi sqlalchemy
```

#### 导出依赖

```bash
# 导出所有依赖
uv pip freeze > requirements.txt

# 导出特定格式
uv pip freeze --format pip > requirements.txt
uv pip freeze --format json > requirements.json
```

#### 环境变量配置

```bash
# ~/.bashrc or ~/.zshrc
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_CACHE_DIR=$HOME/.cache/uv
export UV_PYTHON=python3.11
```

---

## 4. 本地开发环境

### 4.1 完整开发环境搭建

```bash
# 1. 安装 UV（参考 3.2 节）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 克隆项目
git clone https://github.com/zleap-team/dataflow.git
cd dataflow

# 3. 创建虚拟环境
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 4. 同步所有依赖（推荐方式）
uv sync --all-extras

# 或者使用传统方式
# uv pip install -e ".[dev,api]"

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 6. 启动依赖服务（MySQL, ES, Redis）
docker-compose up -d mysql elasticsearch redis

# 7. 等待服务启动（约30秒）
sleep 30

# 8. 初始化数据库
python scripts/init_database.py
python scripts/init_elasticsearch.py

# 9. 运行应用
uvicorn dataflow.api.main:app --reload --host 0.0.0.0 --port 8000

# 10. 验证服务
curl http://localhost:8000/health
```

### 4.2 开发命令速查

```bash
# 依赖管理
uv sync                          # 同步依赖
uv pip list                      # 列出已安装的包
uv pip install package_name      # 安装新包

# 代码质量
black dataflow/                 # 代码格式化
ruff check dataflow/            # 代码检查
mypy dataflow/                  # 类型检查
pytest                           # 运行测试

# 服务管理
docker-compose up -d             # 启动依赖服务
docker-compose logs -f api       # 查看API日志
docker-compose restart api       # 重启API服务
docker-compose down              # 停止所有服务

# 数据库操作
python scripts/init_database.py    # 初始化MySQL
python scripts/init_elasticsearch.py  # 初始化ES
python scripts/migrate.py          # 数据库迁移
```

---

## 5. 配置管理

### 5.1 环境配置优先级

```
环境变量 > .env文件 > 默认配置
```

### 5.2 多环境配置

```bash
# 开发环境
cp .env.development .env

# 生产环境
cp .env.production .env
```

**.env.production** 示例:

```ini
DEBUG=false
LOG_LEVEL=INFO
MYSQL_HOST=mysql-prod.example.com
LLM_MODEL=sophnet/Qwen3-30B-A3B-Thinking-2507

# 生产环境安全配置
MYSQL_PASSWORD=<strong_password>
REDIS_PASSWORD=<strong_password>
```

---

## Docker

...

---