# ベースイメージを指定
FROM python:3.9

# 作業ディレクトリを設定
WORKDIR /app

# 必要なパッケージをインストール
COPY requirements.txt .
RUN pip install -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# スクリプトに実行権限を付与
RUN chmod +x start.sh

# アプリケーションを起動
CMD ["./start.sh"]
