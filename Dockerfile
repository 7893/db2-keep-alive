# 基于官方 Python 镜像
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    libaio1 \
    unzip \
    curl \
 && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 拷贝依赖和源码
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 clidriver
RUN curl -L -o clidriver.zip "https://public.dhe.ibm.com/ibmdl/export/pub/software/data/db2/drivers/odbc_cli/linuxx64_odbc_cli.tar.gz" \
 && mkdir -p /opt/ibm/clidriver \
 && tar -xzvf clidriver.zip -C /opt/ibm/clidriver --strip-components=1 \
 && rm clidriver.zip

# 设置环境变量供 ibm_db 使用
ENV IBM_DB_HOME=/opt/ibm/clidriver
ENV LD_LIBRARY_PATH=/opt/ibm/clidriver/lib

# 拷贝源码
COPY . .

# 使用 gunicorn 启动 Flask 应用（监听 Cloud Run 指定端口）
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "main:app"]
