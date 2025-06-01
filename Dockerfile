# 基于官方 Python 镜像
FROM python:3.11-slim

# 安装必要系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    libaio1 \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 clidriver 到 /opt/ibm/clidriver
RUN mkdir -p /opt/ibm && \
    curl -L -o /tmp/clidriver.tar.gz "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/linuxx64_odbc_cli.tar.gz" && \
    tar -xzf /tmp/clidriver.tar.gz -C /opt/ibm && \
    rm /tmp/clidriver.tar.gz

# 设置环境变量（关键！）
ENV IBM_DB_HOME=/opt/ibm/clidriver
ENV LD_LIBRARY_PATH=/opt/ibm/clidriver/lib
ENV PATH="${IBM_DB_HOME}/bin:$PATH"

# 拷贝源代码
COPY . .

# 使用 gunicorn 启动 Flask 应用，监听 Cloud Run 提供的 $PORT
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "main:app"]

