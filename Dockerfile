# 基于官方 Python 3.11 精简镜像
FROM python:3.11-slim

# 安装系统依赖（含 UTF-8 支持 + gcc + clidriver 依赖）
RUN apt-get update && apt-get install -y \
    gcc \
    libaio1 \
    curl \
    ca-certificates \
    unzip \
    locales \
    && rm -rf /var/lib/apt/lists/* \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && locale-gen

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# 设置工作目录
WORKDIR /app

# 拷贝并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 clidriver 到 /opt/ibm/clidriver
RUN mkdir -p /opt/ibm && \
    curl -L -o /tmp/clidriver.tar.gz "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/linuxx64_odbc_cli.tar.gz" && \
    tar -xzf /tmp/clidriver.tar.gz -C /opt/ibm && \
    rm /tmp/clidriver.tar.gz

# 设置 ibm_db 所需环境变量
ENV IBM_DB_HOME=/opt/ibm/clidriver
ENV LD_LIBRARY_PATH=/opt/ibm/clidriver/lib
ENV PATH="/opt/ibm/clidriver/bin:$PATH"

# 拷贝应用代码
COPY . .

# 使用 gunicorn 启动 Flask 应用，监听 Cloud Run 的端口
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "main:app"]

