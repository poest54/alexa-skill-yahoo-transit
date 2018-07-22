# Amazon Alexa Skill: Yahoo Transit

Amazon Alexaスキル：Yahoo!路線情報を利用して、電車検索を行う。

## Description

Amazon Alexaに駅名や日時など条件を伝え、[Yahoo!路線情報](https://transit.yahoo.co.jp/)で検索し、見つかった最初のルートを返す。

尚、本プログラムを作成するにあたり、下記のサイトを参考にさせてもらいました。

- [[Amazon Echo] AlexaにYahoo路線情報を聴けるようにした](https://qiita.com/Sa2Knight/items/a7eb54b6fe8a809dffc8)
- [[RaspberryPi][python]温度センサー＋IFTTTで室温をLINEに知らせる](https://qiita.com/jun1_0803/items/95cec2f149bdec82472d)

## Requirement

- 検索した路線情報を Line へ通知するために、[IFTTT](https://ifttt.com/line)、[Line Notify](https://notify-bot.line.me/ja/)のサービスを利用しています。
- IFTTTのWebhooksキーを暗号化するため、AWS Key Management Serviceを利用しています。

## Usage

- 開始
  - 「ヤフー路線をひらいて」
- 検索例
  - 「渋谷駅から海浜幕張駅まで」
    - 「15分後に出発」
    - 「明日の朝9時45分に到着」
    - 「今日の終電」
    - 「8月1日の始発」
- 結果
  - 「xx時xx分に渋谷駅を発車する、xx行きに乗車すると、xx時xx分に海浜幕張駅に到着します。料金はxx円で、xx回の乗り換えがあります。

## Install

1. （Line通知が必要な場合）[IFTTT](https://ifttt.com/line)、[Line Notify](https://notify-bot.line.me/ja/)のサービスに登録
    - Line通知が不要な場合は、Line Notifyに関連するグローバル変数にダミーの値を入れるなど変更する必要があります。
2. AWS LambdaへアップロードするZIPファイルを作成

    ~~~bash
    ZIPファイル作成例:
    $ mkdir lambda_upload
    $ cp /path/to/yahoo_transit.py .
    $ cd lambda_upload/
    $ pip3 install requests -t .
    $ pip3 install BeautifulSoup4 -t .
    $ zip lambda_upload.zip *
    ~~~

3. AWS Lambdaを作成
4. Amazon Alexaスキルを作成
    - サンプル）設定値JSONファイル： resources/AlexaSkillYahooTransit.json
5. AWS Lambda単体でテスト
    - サンプル）テストイベント用JSONファイル resources/AlexaIntentXXX.json

## Author

[poest54](https://github.com/poest54)
